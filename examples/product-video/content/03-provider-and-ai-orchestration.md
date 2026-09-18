# Provider and AI orchestration

LaunchFrame can use company AI resources through Pi providers.

Supported provider channels include:

- CodeMie Web / Platform through company SSO;
- CodeMie CLI through the same CodeMie SSO channel;
- DIAL through a validated token and provider network access;
- ELITEA through a validated Personal Access Token.

The selected Provider controls the live model catalog. The selected model is used for Draft generation and, when it supports image input, Vision analysis.

Provider tokens are not stored in the product resource directory. When remembered, DIAL and ELITEA credentials use the local Windows credential store.
