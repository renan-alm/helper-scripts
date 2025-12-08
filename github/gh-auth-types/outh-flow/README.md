# GitHub OAuth Token Management

Scripts for managing GitHub User Access Tokens via OAuth with GitHub Apps.

## Pre-requisites

1. A GitHub App must be created. For my purposes, I am using [demo-app-renan](https://github.com/organizations/renan-org/settings/apps/demo-app-renan).

2. Install the App in a Org (for practical testing).

3. Generate a Client Secret for the App.

## Token Management Flows

### 1. Authorization Flow

Generate authorization URL for user to grant permission.

```bash
./ghapp-user-token.py --client-id YOUR_ID --client-secret YOUR_SECRET --ngrok-url <ngrok-url>
```

Provide your ngrok URL (e.g., `https://abc123.ngrok.io`) or leave it as default for localhost. 
Example: 
```
https://github.com/login/oauth/authorize?client_id=Iv23liouHxYEUmRDDfij&redirect_uri=https://defamatorily-unprosaical-stefani.ngrok-free.dev/callback&scope=repo,user
```


### 2. Exchange Code for Tokens

Exchange authorization code for access token and refresh token.

```bash
./ghapp-user-token.py --client-id YOUR_ID --client-secret YOUR_SECRET --code v12d2dvsadjkandw2
```

### 3. Refresh Access Token

Get new access token and refresh token using existing refresh token.

```bash
./ghapp-user-token.py --client-id YOUR_ID --client-secret YOUR_SECRET --refresh-token ghr_xxxxx
```

### 4. Revoke Token

Invalidate access token or refresh token.

```bash
./ghapp-user-token.py --client-id YOUR_ID --client-secret YOUR_SECRET --revoke gho_xxxxx
```

## Token Management Parameters

- `--ngrok-url` - ngrok public URL or localhost (default: `http://localhost:3000`)
- `--scope` - OAuth scopes (default: `repo,user`)

## Supporting Tools

- `oauth-callback-server.py` - Listens on localhost:3000 to capture authorization code
- `../create-app-token.py` - Generates GitHub App tokens (JWT-based)

## Callback Server Setup with Ngrok

The `callback-server.py` is a lightweight Python HTTP server that listens on `localhost:3000` and automatically captures the OAuth authorization code returned by GitHub after a user grants permission. This eliminates the need to manually copy codes from redirect URLs.

#### Step 1: Start the Callback Server

Open a terminal and run:

```bash
python callback-server.py --port 3000
```

Expected output:

```text
OAuth callback server listening on http://localhost:3000
Waiting for GitHub authorization callback...
Press Ctrl+C to stop the server
```

#### Step 2: Expose Localhost with Ngrok

In a **new terminal**, expose your local server to the public internet:

```bash
ngrok http 3000
```

Expected output:

```text
ngrok                                                   (Ctrl+C to quit)

Session Status                online
Account                       you@example.com
Version                       3.x.x
Region                        us (United States)
Forwarding                    https://XXXX-XX-XXX-XXX-XX.ngrok.io -> http://localhost:3000
```

#### Step 3: Generate Authorization URL

In a **third terminal**, generate the authorization URL as explained in the previous main section of this document.

```bash
./ghapp-user-token.py \
  --client-id YOUR_CLIENT_ID \
  --client-secret YOUR_CLIENT_SECRET \
  --redirect-uri https://XXXX-XX-XXX-XXX-XX.ngrok.io/callback
```

This will output an authorization URL:

```text
Visit: https://github.com/login/oauth/authorize?client_id=Ov23liXXXXXXXXXX&redirect_uri=https://XXXX-XX-XXX-XXX-XX.ngrok.io/callback&scope=repo,user
```


---------
