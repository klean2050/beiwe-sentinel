""" Simulates Beiwe phones for the Sentinel demo: registers participants through /register_user and
uploads encrypted data files through /upload, the same HTTP calls and file encryption the iOS and
Android apps use. All data is synthetic. """
import base64
import hashlib
import json
import math
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from Cryptodome.Cipher import AES
from Cryptodome.PublicKey import RSA

SERVER = "http://127.0.0.1:8080"
TZ = ZoneInfo("America/Los_Angeles")
NEW_PASSWORD = "SentinelPhone1"

b64 = lambda b: base64.urlsafe_b64encode(b).replace(b"\n", b"")
device_hash = lambda s: b64(hashlib.sha256(s.encode()).digest()).decode()


class Phone:
    def __init__(self, patient_id: str, temp_password: str, os_name: str, seed: int):
        self.pid, self.temp, self.os = patient_id, temp_password, os_name
        self.suffix = "/ios" if os_name == "ios" else ""
        self.device_id = f"sim-{os_name}-{patient_id}"
        self.rng = random.Random(seed)
        self.password = device_hash(temp_password)

    def post(self, endpoint: str, **data):
        data.update(patient_id=self.pid, password=self.password, device_id=self.device_id)
        return requests.post(f"{SERVER}/{endpoint}{self.suffix}", data=data, timeout=60)

    def register(self):
        r = self.post(
            "register_user", phone_number="0000000000", new_password=NEW_PASSWORD,
            device_os="iOS" if self.os == "ios" else "Android",
            os_version="18.6" if self.os == "ios" else "15", beiwe_version="2.6.0",
            model="iPhone15,2" if self.os == "ios" else "Pixel 8", manufacturer="Apple" if self.os == "ios" else "Google",
            timezone="America/Los_Angeles",
        )
        if r.status_code in (401, 403) and not getattr(self, "_retried", False):  # registered by an earlier test
            self._retried = True
            self.password = device_hash(device_hash(NEW_PASSWORD))
            return self.register()
        if r.status_code != 200:
            raise RuntimeError(f"register {self.pid}: {r.status_code} {r.text[:200]}")
        self.password = device_hash(NEW_PASSWORD)
        body = r.json()
        self.key = RSA.import_key(base64.b64decode(body["client_public_key"]))
        return body

    # ---- encryption, mirroring libs/encryption.py DeviceDataDecryptor ----
    def encrypt_file(self, lines: list[str]) -> bytes:
        aes_key = self.rng.randbytes(16)
        m = int.from_bytes(b64(aes_key), "big")
        rsa_blob = pow(m, self.key.e, self.key.n).to_bytes(self.key.size_in_bytes(), "big")
        out = [b64(rsa_blob)]
        for line in lines:
            raw = line.encode()
            pad = 16 - len(raw) % 16
            raw += bytes([pad]) * pad
            iv = self.rng.randbytes(16)
            out.append(b64(iv) + b":" + b64(AES.new(aes_key, AES.MODE_CBC, iv=iv).encrypt(raw)))
        return b"\n".join(out)

    def upload(self, name_parts: list[str], ts_ms: int, lines: list[str]):
        file_name = "_".join([self.pid, *name_parts, str(ts_ms)]) + ".csv"
        r = self.post("upload", file_name=file_name, file=self.encrypt_file(lines).decode())
        if r.status_code != 200:
            print("upload failed", file_name, r.status_code, r.text[:120])
        return r


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def utc_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def simulate(phone: Phone, days: int, study: dict, profile: dict):
    rng = phone.rng
    ios = phone.os == "ios"
    home = profile["home"]
    work = profile["work"]
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {}

    def bump(k):
        counts[k] = counts.get(k, 0) + 1

    for d in range(days, 0, -1):
        day = today - timedelta(days=d)
        drng = random.Random(f"{phone.pid}-{d}")  # the day's plan, shared by GPS and survey answers
        stays_home = drng.random() < profile["p_home_day"]
        leave = day + timedelta(hours=8 + drng.random() * 2)
        back = day + timedelta(hours=16.5 + drng.random() * 3)
        errand = None if stays_home or drng.random() < 0.5 else (back + timedelta(hours=1), profile["errand"])

        def where(t: datetime):
            if errand and errand[0] <= t < errand[0] + timedelta(minutes=50):
                return errand[1]
            if stays_home or not (leave <= t < back):
                return home
            frac = (t - leave).total_seconds() / 1800
            if frac < 1:  # commuting for 30 minutes
                return (home[0] + (work[0] - home[0]) * frac, home[1] + (work[1] - home[1]) * frac)
            return work

        # GPS: 90 seconds on, 810 off -> one burst every 15 minutes at about one fix per second
        gps = ["timestamp,latitude,longitude,altitude,accuracy" if ios else "timestamp, latitude, longitude, altitude, accuracy"]
        t = day
        while t < day + timedelta(days=1):
            if rng.random() < profile["gps_coverage"]:
                for k in range(90):
                    tt = t + timedelta(seconds=k)
                    lat, lon = where(tt)
                    gps.append(f"{ms(tt)},{lat + rng.gauss(0, 0.00012):.6f},{lon + rng.gauss(0, 0.00012):.6f},{80 + rng.gauss(0, 3):.1f},{rng.uniform(5, 25):.1f}")
            t += timedelta(minutes=15)
        phone.upload(["gps"], ms(day), gps); bump("gps")

        # Accelerometer: a 10 s burst at 10 Hz every 30 minutes
        acc = ["timestamp,accuracy,x,y,z"]
        t = day
        while t < day + timedelta(days=1):
            moving = 7 <= t.hour < 22 and rng.random() < 0.35
            for k in range(100):
                tt = t + timedelta(milliseconds=100 * k)
                amp = 0.35 * math.sin(k / 1.6) if moving else 0.01
                acc.append(f"{ms(tt)},unknown,{rng.gauss(0, 0.02) + amp:.4f},{rng.gauss(0, 0.02):.4f},{rng.gauss(-1, 0.02) + amp / 2:.4f}")
            t += timedelta(minutes=30)
        phone.upload(["accel"], ms(day), acc); bump("accel")

        # Screen on/off
        pw = ["timestamp,event,level" if ios else "timestamp, event"]
        for _ in range(rng.randint(25, 60)):
            tt = day + timedelta(hours=7 + rng.random() * 16)
            pw.append(f"{ms(tt)},Unlocked,0.{rng.randint(20, 99)}" if ios else f"{ms(tt)},Screen turned on")
        phone.upload(["powerState"], ms(day), [pw[0], *sorted(pw[1:])]); bump("powerState")

        if not ios:  # call and text logs exist only on Android
            calls = ["hashed phone number,call type,timestamp,duration in seconds"]
            for _ in range(rng.randint(0, 6)):
                calls.append(f"{b64(rng.randbytes(12)).decode()},{rng.choice(['Incoming Call', 'Outgoing Call', 'Missed Call'])},{ms(day + timedelta(hours=8 + rng.random() * 13))},{rng.randint(0, 900)}")
            phone.upload(["callLog"], ms(day), calls); bump("callLog")
            texts = ["timestamp,hashed phone number,sent vs received,message length,time sent"]
            for _ in range(rng.randint(2, 25)):
                tt = day + timedelta(hours=8 + rng.random() * 14)
                texts.append(f"{ms(tt)},{b64(rng.randbytes(12)).decode()},{rng.choice(['sent SMS', 'received SMS'])},{rng.randint(4, 160)},{ms(tt)}")
            phone.upload(["textsLog"], ms(day), [texts[0], *sorted(texts[1:])]); bump("textsLog")

        # Surveys: answer each scheduled tracking survey with the participant's adherence rate
        for survey in study["surveys"]:
            if survey["survey_type"] != "tracking_survey":
                continue
            weekday = (day.weekday() + 1) % 7  # Beiwe timings start on Sunday
            for sec in survey["timings"][weekday]:
                if rng.random() > profile["adherence"]:
                    continue
                opened = day + timedelta(seconds=sec, minutes=rng.randint(1, 40))
                answers = answer_survey(survey, rng, stays_home, profile)
                rows = ["question id,question type,question text,question answer options,answer"]
                timing_rows = []
                tt = opened
                for q, text_opts, ans in answers:
                    rows.append(csv_row([q["question_id"], q["question_type"], q.get("question_text", ""), text_opts, ans]))
                    tt += timedelta(seconds=rng.randint(3, 12))
                    timing_rows.append(f"{ms(tt)}," + csv_row([q["question_id"], q["question_type"], q.get("question_text", ""), text_opts, ans]) + (",answered" if ios else ""))
                submitted = tt + timedelta(seconds=4)
                header = "timestamp,question id,question type,question text,question answer options,answer" + (",event" if ios else "")
                timing_rows.insert(0, f"{ms(opened)},,,,,Survey first rendered and displayed to user" + ("," if ios else ""))
                timing_rows.append(f"{ms(submitted)},,,,,User hit submit" + ("," if ios else ""))
                phone.upload(["surveyAnswers", survey["object_id"]], ms(submitted), rows); bump("surveyAnswers")
                phone.upload(["surveyTimings", survey["object_id"]], ms(opened), [header, *timing_rows]); bump("surveyTimings")
    return counts


def csv_row(values):
    out = []
    for v in values:
        v = str(v).replace("\n", " ")
        out.append(f'"{v}"' if ("," in v or '"' in v) else v)
    return ",".join(out)


def answer_survey(survey, rng, stays_home, profile):
    """ Produces (question, answer-options text, answer) triples honoring display_if. """
    chosen = {}
    result = []
    for q in survey["content"]:
        qt = q["question_type"]
        if qt == "info_text_box":
            continue
        cond = q.get("display_if")
        if cond and not check(cond, chosen):
            result.append((q, options_text(q), "NOT_PRESENTED"))
            continue
        if qt == "slider":
            lo, hi = int(q["min"]), int(q["max"])
            mid = lo + (hi - lo) * (profile["mood"] if "stress" not in q["question_id"] else 1 - profile["mood"])
            v = max(lo, min(hi, round(rng.gauss(mid, (hi - lo) / 6))))
            chosen[q["question_id"]] = v
            result.append((q, options_text(q), v))
        elif qt == "radio_button":
            n = len(q["answers"])
            if q["question_id"] == "ema-where":
                i = 0 if stays_home or rng.random() < 0.45 else rng.randint(1, n - 1)
            elif q["question_id"] == "hs-left":
                i = 0 if stays_home else 1
            else:
                i = rng.randint(0, n - 1)
            chosen[q["question_id"]] = i
            result.append((q, options_text(q), q["answers"][i]["text"]))
        elif qt == "checkbox":
            picks = sorted(rng.sample(range(len(q["answers"])), rng.randint(1, 2)))
            chosen[q["question_id"]] = picks
            result.append((q, options_text(q), "[" + "; ".join(q["answers"][i]["text"] for i in picks) + "]"))
        elif qt == "free_response":
            if q.get("text_field_type") == "NUMERIC":
                v = rng.randint(0, 4) if q["question_id"] == "sl-wakings" else round(rng.uniform(1, 9), 1)
                result.append((q, options_text(q), v))
            else:
                result.append((q, options_text(q), "NO_ANSWER_SELECTED" if rng.random() < 0.7 else "Busy day"))
        elif qt == "time":
            h = rng.randint(22, 24) if q["question_id"] == "sl-bed" else rng.randint(6, 8)
            result.append((q, options_text(q), f"{h % 24}:{rng.choice(['00', '15', '30', '45'])}"))
        else:
            result.append((q, options_text(q), "NO_ANSWER_SELECTED"))
    return result


def check(node, chosen):
    op = next(iter(node))
    p = node[op]
    if op == "and":
        return all(check(x, chosen) for x in p)
    if op == "or":
        return any(check(x, chosen) for x in p)
    if op == "not":
        return not check(p, chosen)
    qid, target = p
    a = chosen.get(qid)
    if a is None:
        return False
    vals = a if isinstance(a, list) else [a]
    f = {"==": lambda x: x == target, "<": lambda x: x < target, "<=": lambda x: x <= target,
         ">": lambda x: x > target, ">=": lambda x: x >= target}[op]
    return any(f(v) for v in vals)


def options_text(q):
    if "answers" in q:
        return "[" + "; ".join(a["text"] for a in q["answers"]) + "]"
    if q["question_type"] == "slider":
        return f"min = {q['min']}; max = {q['max']}"
    if q["question_type"] == "free_response":
        return f"Text-field input type = {q.get('text_field_type', 'MULTI_LINE_TEXT')}"
    return ""


if __name__ == "__main__":
    participants_path, surveys_path = sys.argv[1], sys.argv[2]
    info = json.load(open(participants_path))
    surveys = json.load(open(surveys_path))  # surveys with object_ids, exported from the server
    # Fictional places in the Los Angeles area; the work site and errand stop differ per person.
    profiles = [
        dict(home=(34.0617, -118.2035), work=(34.0224, -118.2851), errand=(34.0522, -118.2437), p_home_day=0.15, adherence=0.85, mood=0.68, gps_coverage=0.95),
        dict(home=(34.1016, -118.3267), work=(34.0736, -118.4004), errand=(34.0900, -118.3600), p_home_day=0.3, adherence=0.7, mood=0.55, gps_coverage=0.8),
        dict(home=(33.9850, -118.4695), work=(34.0195, -118.4912), errand=(34.0000, -118.4800), p_home_day=0.6, adherence=0.55, mood=0.4, gps_coverage=0.9),
        dict(home=(34.1478, -118.1445), work=(34.0686, -118.4452), errand=(34.1400, -118.1300), p_home_day=0.1, adherence=0.9, mood=0.72, gps_coverage=0.6),
    ]
    phones = [p for p in info["participants"] if p["os"]]
    for i, p in enumerate(phones):
        phone = Phone(p["patient_id"], p["password"], p["os"], seed=100 + i)
        phone.register()
        t0 = time.time()
        counts = simulate(phone, p["days_ago"], surveys, profiles[i])
        print(p["patient_id"], p["os"], counts, f"{time.time() - t0:.0f}s")
