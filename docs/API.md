# Finance Friend API

The maintained API reference is the shared doc:
**[Finance Friend API Reference](https://claude.ai/code/artifact/409f73bb-9e7f-4c08-8141-fa8f8e330c25)**.
It covers auth, OTP rules and the 5 onboarding screens, with a curl example and a real response for each API.
When an API changes, update that doc and add a row to its changelog.

Also available:

- **Swagger UI** at `http://localhost:8000/docs` (generated from the code, so it's always current). ReDoc is at `/redoc`.
- **`docs/api_examples.sh`** runs the whole flow against a running server: auth token → OTP → Money → Equity → Risk → Goals → Preferences → dashboard.

  ```bash
  ./docs/api_examples.sh                              # http://localhost:8000
  BASE_URL=http://staging.example.com ./docs/api_examples.sh
  ```
