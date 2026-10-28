# Deploying the Sentinel Beiwe server on AWS

This guide sets up a Beiwe backend that you own: the researcher website, the server the phones upload to, the database, file storage and Forest processing, all in your AWS account. It follows the deployment tooling in [onnela-lab/beiwe-backend](https://github.com/onnela-lab/beiwe-backend) (`cluster_management/launch_script.py`), as of October 2026. If anything here disagrees with the backend's own README or wiki, follow those. The backend is a rolling release and its tooling changes.

To try the website locally before you have AWS access, see [`../server-demo`](../server-demo).

## What you end up with

```
 Phones (Beiwe2 app or your own build)          Researchers (browser)
                 \                                  /
                  https://sentinel.<your-domain>  (SSL certificate from ACM)
                                  |
                       Load balancer (Elastic Beanstalk)
                                  |
              Web servers: 1–2 × t3.medium, Python 3.12, Amazon Linux 2023
                 |                                   |
     PostgreSQL (RDS, m5.large,          S3 bucket (encrypted uploads
     encrypted, 35-day backups)           and processed data)
                 |
     Manager server (t3.medium): data processing, push notifications, Forest
     Optional worker servers (m5.large) for large studies
```

The launch script creates the database, bucket, servers, security groups and IAM roles. You add the certificate, DNS record and push-notification credentials.

| | |
|---|---|
| Hands-on time | About one working day for someone comfortable with AWS and a terminal, plus waiting on approvals |
| Monthly cost | Roughly $250–350 at the script's default sizes. This is an estimate, not a quote; check it with the AWS Pricing Calculator. The database (m5.large) is the largest item and can be downsized for a pilot. |
| Ongoing work | An hour or two a month for updates and checks. Someone must own this. |

## 0. Before you start

Start the items with long lead times first.

| Item | Why | Who / lead time |
|---|---|---|
| AWS account covered by a Business Associate Agreement (BAA), ideally USC's HIPAA-eligible account | The server holds identifiable data such as GPS and voice | USC ITS or ISO; weeks |
| IRB approval of the data plan (storage location, retention, who has access) | Required for the study | Weeks |
| A domain or subdomain, for example `sentinel.<lab>.usc.edu` | The phones refuse to upload without SSL, and SSL needs a domain | USC ITS or the lab's DNS admin; days |
| Push-notification credentials | Without them, iPhones get no survey notifications and some scheduling features are off. For the store app, email the Onnela lab maintainer (see [beiwe-backend issue #100](https://github.com/onnela-lab/beiwe-backend/issues/100)). For your own app build, use your own Firebase project. | Days |
| Sentry account, with 3 project DSNs | The launch script refuses to run without valid Sentry DSNs. Error reports can contain request data, so ask USC security whether Sentry is acceptable. Sentry offers a BAA on paid plans. | An hour |
| A named system administrator | Gets the server's admin email and does updates | |

## 1. Workstation setup (one time)

On a Mac or Linux machine, or WSL on Windows:

1. Install `git`, the [AWS EB CLI](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3-install.html) and Python.
   - The web servers run Python 3.12. The launch script's dependency `fabric3` is old. The backend wiki's deployment page lists the Python version for the launch script (3.8 when last checked), so use a separate virtual environment at that version for it.
2. Clone the backend:
   ```bash
   git clone https://github.com/onnela-lab/beiwe-backend.git
   ```
   ```bash
   cd beiwe-backend/cluster_management
   ```
3. Install the launch script's requirements in that virtual environment:
   ```bash
   pip install -r launch_requirements.txt
   ```

## 2. Prepare the AWS account

1. **Pick one region** and keep everything in it, for example `us-west-2`.
2. **Create an IAM user for deployment** with the `AdministratorAccess` policy, which the backend's instructions require, and create an access key for it. Store the key in a password manager, never in git or chat. Once the deployment works, consider disabling the key until the next update.
3. **Create an EC2 key pair** (EC2 → Key Pairs) and download the `.pem` file:
   ```bash
   chmod 600 /path/to/sentinel-deploy.pem
   ```
4. **Note the default VPC ID** for the region (VPC → Your VPCs).
5. **Request an SSL certificate** in AWS Certificate Manager for your domain, in the same region, and complete the domain validation.

## 3. Configure the launch script

All paths are inside `beiwe-backend/cluster_management/`. These files contain secrets and are git-ignored by the backend; keep it that way.

1. Copy and fill in the AWS credentials:
   ```bash
   cp general_configuration/aws_credentials.example.json general_configuration/aws_credentials.json
   ```
   Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to the deployment user's key.
2. Copy and fill in the global configuration:
   ```bash
   cp general_configuration/global_configuration.example.json general_configuration/global_configuration.json
   ```
   | Key | Value |
   |---|---|
   | `DEPLOYMENT_KEY_NAME` | Name of the EC2 key pair from step 2.3 |
   | `DEPLOYMENT_KEY_FILE_PATH` | Absolute path to the `.pem` file |
   | `VPC_ID` | Default VPC ID from step 2.4 |
   | `AWS_REGION` | For example `us-west-2` |
   | `SYSTEM_ADMINISTRATOR_EMAIL` | The administrator's email, shown in the website footer |
3. Generate the environment files. Pick a short environment name such as `sentinel`; AWS resources are named after it.
   ```bash
   python launch_script.py -help-setup-new-environment
   ```
4. In `environment_configuration/`, edit the two new files:
   - `sentinel_beiwe_environment_variables.json`: set `DOMAIN` to your domain without `https://`, for example `sentinel.<lab>.usc.edu`, and the three Sentry DSNs.
   - `sentinel_server_settings.json`: server sizes. The defaults are `t3.medium` web and manager servers, `m5.large` workers and an `m5.large` database. For a pilot of a few dozen participants, a smaller database is likely fine; for a large study, keep or raise the defaults.

## 4. Create the cluster

From `cluster_management/`, in this order:

1. Create the database, bucket and web environment. This takes 20–40 minutes and generates more credential files in `environment_configuration/`. **Back that folder up securely**, because it holds the database password.
   ```bash
   python launch_script.py -create-environment
   ```
2. Point the EB CLI at the new environment. From the repository root, run `eb init`, choose the same region and the application the script created, then select the environment:
   ```bash
   eb use sentinel
   ```
3. **Turn on HTTPS before deploying code.** In the AWS console under EC2 → Load Balancers, find the environment's load balancer and add an HTTPS listener on port 443 that uses your ACM certificate, forwarding to the instances as the backend README describes. If the script's output or the README mentions encrypting the load-balancer-to-server leg (port 443 to the instances), follow that instead.
4. Deploy the code to the web servers. The first deploy also sets up the database tables.
   ```bash
   eb deploy
   ```
5. **Create the DNS record** for your domain pointing at the load balancer: a CNAME for a subdomain, or a Route 53 alias for a root domain.
6. Create the manager server, which runs data processing, push notifications and Forest:
   ```bash
   python launch_script.py -create-manager
   ```
   If the manager's disk fills up with Forest jobs, set this before creating it (default 20 GB):
   ```bash
   export OVERRIDE_PROCESSING_SERVER_STORAGE_GB=100
   ```
   Only large studies need worker servers:
   ```bash
   python launch_script.py -create-worker
   ```

If deploys fail on health-check permissions, run `python launch_script.py -fix-health-checks-blocking-deployment`. The backend documents `-purge-instance-profiles` as a last resort for a failed first setup only. Never run it on a working cluster.

## 5. First login and hardening

**Do this before the DNS record in step 4.5 makes the site public, or right after.** The first database setup creates a site administrator named `default_admin` with the password `abcABC123!@#`. That password is written in the backend's public code (`database/migrations/0005_add_admin_user.py`), so anyone can look it up.

1. Log in as `default_admin`. You can use the Elastic Beanstalk environment URL from the console before DNS is set up; your browser may warn about the certificate there.
2. Create your own site administrator account with a password of at least 20 characters, which site administrators must use.
3. Log in as yourself. Then delete `default_admin`, or at minimum give it a long random password.
4. Turn on two-factor login (MFA) for your account under Manage Credentials. For each study, consider requiring MFA in its security settings.
5. Under Firebase Credentials, upload the push-notification credentials from section 0.
6. Create researcher accounts. Give each person the lowest role they need: study admin or researcher.

## 6. Set up the Sentinel study

1. Create the study (Manage Studies → Create study). Set its time zone to `America/Los_Angeles`.
2. Import the Sentinel settings and surveys. On the study's edit page, import a study settings JSON. [`../server-demo/sentinel_study.json`](../server-demo/sentinel_study.json) has the prototype's surveys and settings in the right format. Replace the example questions and consent text with your approved versions first.
3. Add the study dates (for example the baseline visit) and custom fields (for example Site and Cohort).
4. Turn on Forest for the study if you want daily summaries, then start Jasmine, Willow and Sycamore jobs from the Forest menu.
5. Run a pilot: create a few participants, install Beiwe2 on test iPhones and Android phones, register them against `https://<your-domain>`, and check the dashboards over several days.

## 7. Connect the analysis notebooks in this repository

The notebooks in `../code/forest_mano/` read data through the API. In `../code/forest_mano/keyring_studies.py`, set:

- `BEIWE_URL` to `https://<your-domain>`
- the username and password of a researcher account
- an API key pair from Manage Credentials → Generate a New API Key (the secret is shown only once)

Keep the filled-in file out of git.

## 8. Updating the server

The backend is updated continuously from its `main` branch. Watch its GitHub issues for `ANNOUNCEMENT` and `Infrastructure` posts. To update:

1. Terminate the processing servers:
   ```bash
   python launch_script.py -terminate-processing-servers
   ```
2. Pull the latest backend code:
   ```bash
   git pull origin main
   ```
3. Update the web servers. Wait for this to finish, because it may update the database.
   ```bash
   eb deploy
   ```
4. Recreate the manager, and any workers:
   ```bash
   python launch_script.py -create-manager
   ```

Avoid updating during busy study periods, and check the dashboards afterwards.

## Security checklist

- [ ] AWS account covered by a BAA; deployment key stored in a password manager and disabled when not in use
- [ ] HTTPS working; plain HTTP not used by any phone or researcher
- [ ] `default_admin` deleted or given a long random password; MFA on for all site administrators
- [ ] `cluster_management/environment_configuration/` backed up securely and never committed
- [ ] RDS backups (35 days by default) and S3 encryption confirmed in the AWS console
- [ ] Sentry use approved by USC security, or replaced
- [ ] Researcher accounts reviewed each quarter; accounts of people who leave removed
- [ ] Data retention and deletion plan matches the IRB protocol
