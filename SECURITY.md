# Security

## Reporting a problem

Please don't open a public issue for a security problem. Report it privately through GitHub instead: on the repository's **Security** tab, choose **Report a vulnerability**. Say what you found, how to reproduce it, and which version you're running (shown at the top of the web UI, or `docker exec -it staffpicked staffpicked --version`).

You'll get an answer within a week. Once a fix is out, the release notes credit you unless you'd rather they didn't.

## Supported versions

Only the latest release gets security fixes. Update by pulling the newest image and recreating the container; your `/config` folder carries over.

## What StaffPicked protects

- The web UI holds your media server and API keys, so it asks for a password, and without one it only opens for browsers on your local network that connect to it directly. See the README's [Security](README.md#security) section for sign-in, two-factor codes and reverse proxy setup.
- Passwords, sign-ins and recovery codes are stored only as hashes. API keys are stored as you enter them in `staffpicked.env`, so keep the config folder private.
- StaffPicked runs as an unprivileged user in the container and needs no extra capabilities.

Problems in Emby, Jellyfin, or the services StaffPicked connects to belong with those projects.
