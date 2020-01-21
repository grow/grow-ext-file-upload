# grow-ext-file-upload

[![Build Status](https://travis-ci.org/grow/grow-ext-file-upload.svg?branch=master)](https://travis-ci.org/grow/grow-ext-file-upload)

A Google App Engine microservice to support file uploads for static websites.

## Concept

1. The microservice uses the App Engine app's identity to create a temporary signed URL. The upload destination is validated and and normalized.
1. The frontend uses the signed URL to upload the file directly to Google Cloud Storage.
1. The frontend can then, separately record the uploaded destination (i.e. by submitting it through a form).

## Usage

1. Clone this repository.
1. Use `make project=GCP_PROJECT deploy` to deploy a standalone service.
1. Ensure the CORS policy is updated: `make bucket=BUCKET cors`. (Update `cors-policy.json` to restrict origins.)

By default, files are uploaded to:

```
/{application-default bucket}/grow-ext-file-upload/{timestamp}/{file}.{ext}
```

The upload destination can be customized by using env variables:

- `GROW_FILE_UPLOAD_BUCKET` – Override the bucket
- `GROW_FILE_UPLOAD_FOLDER` – Override the subfolder

Ensure the application-default service account has access to create files in the appropriate bucket.
