from google.appengine.api import app_identity
import google_storage_signer
import json
import logging
import numpy
import mimetypes
import os
import urllib
import time
import webapp2

BUCKET_NAME = os.getenv('GROW_FILE_UPLOAD_BUCKET', app_identity.get_default_gcs_bucket_name())
FOLDER = os.getenv('GROW_FILE_UPLOAD_FOLDER', 'grow-ext-file-upload')


class CreateUploadUrlHandler(webapp2.RequestHandler):

    def json_response(self, data, status=200):
        self.response.set_status(status)
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(data))

    def get(self):
        content_length = int(self.request.GET.get('content_length'))
        timestamp = numpy.int64(round(time.time() * 1000000))
        name = self.request.GET.get('name', timestamp).strip('/')
        content_type = mimetypes.guess_type(name)[0];

        if '..' in name or '/' in name:
            self.error(400)
            return

        if FOLDER:
            gs_path_format = '/{bucket}/{folder}/{timestamp}'
            gs_path = gs_path_format.format(bucket=BUCKET_NAME, folder=FOLDER, timestamp=timestamp)
        else:
            gs_path_format = '/{bucket}/{timestamp}'
            gs_path = gs_path_format.format(bucket=BUCKET_NAME, timestamp=timestamp)
        gs_path = os.path.join(gs_path, name)

        signer = google_storage_signer.CloudStorageURLSigner()
        request = signer.create_put(gs_path, content_type, content_length)
        upload_url = request['url'] + '?' + urllib.urlencode(request['params'])
        data = {
            'content_type': content_type,
            'upload_url': upload_url,
            'gs_path': gs_path,
        }
        self.json_response(data)


app = webapp2.WSGIApplication([
  ('/_api/create_upload_url', CreateUploadUrlHandler),
])
