# Sentinel participant app prototype

A clickable, single-file web mock of the Beiwe2 participant app with example Sentinel content. Open `index.html` in any browser; no server or build step is needed.

It reproduces the real app's flow on iPhone and Android:

1. Welcome and registration (study server, user ID, temporary password)
2. Consent sections and consent form
3. Permission prompts (location "Always", notifications, and on Android call/text logs and the battery exception)
4. Main screen with pending surveys and the call button
5. Surveys, one question per screen, with every Beiwe question type (`info_text_box`, `slider`, `radio_button`, `checkbox`, `free_response`, `date`, `time`, `date_time`) and `display_if` skip logic
6. Audio survey (simulated, without the microphone), the About page and the account menu

The control panel simulates push notifications. It also shows the survey schedule, which passive streams each platform collects, and the files the phone would upload (survey answers in the `survey_answers` CSV layout).

## Content

The example study is defined in `SENTINEL_STUDY` inside `index.html`, in Beiwe's study-export JSON format. The surveys and wording are placeholders: replace them with Sentinel's EMA items and IRB-approved text. You can also paste a study export into "Try your own survey" in the page.

## Sources

The wording, colors, question types and skip logic come from [onnela-lab/beiwe-ios](https://github.com/onnela-lab/beiwe-ios) and [onnela-lab/beiwe-android](https://github.com/onnela-lab/beiwe-android). The screens are close approximations, not pixel copies. "Own build (Sentinel)" previews a rebranded app, which would need the lab's app code built and published under your own developer accounts.
