# Providers and models

## Supported Providers

```text
CodeMie Web / Platform
CodeMie CLI
DIAL
ELITEA
```

CodeMie uses company SSO. The SSO credential is persisted in the current Windows user's Pi auth store and is reused after restarting the Web GUI/Pi while its access or refresh credential remains available. If the refresh credential is invalid or removed, click `Login CodeMie SSO` again. DIAL and ELITEA require Provider tokens; DIAL also requires the company VPN. Tokens can be remembered securely in Windows Credential Manager and are never written to project files.

## Model selection

The model list is filtered by the selected Provider. Model details shows the live catalog, capabilities, input types, context, output limits, and prices. Quota is shown per Provider; detailed usage is opened from that Provider row.

## Authentication failures

An invalid or expired DIAL/ELITEA token disables its model list and Draft/Vision actions until a new token is validated. A saved model that disappears from a live catalog is not silently replaced; choose a new model explicitly.

## Pi and model loading

Pi starts automatically when a product resource directory is loaded. Model lists are fetched immediately after Pi starts. A valid stored CodeMie SSO session is reused and refreshed when necessary; if the model list is empty after authentication, click `Refresh status` or reload the directory using `Load selected folder` to retry.
