from google.appengine.api import app_identity
from google.appengine.api import images
from google.appengine.ext import blobstore
from google.appengine.ext import ndb
import google_storage_signer
import json
import logging
import numpy
import mimetypes
import os
import urllib
import uuid
import time
import webapp2

BUCKET_NAME = os.getenv('GROW_FILE_UPLOAD_BUCKET',
                        app_identity.get_default_gcs_bucket_name())
FOLDER = os.getenv('GROW_FILE_UPLOAD_FOLDER', 'grow-ext-file-upload')

IMAGE_EXTENSIONS = (
    '.gif',
    '.jpeg',
    '.jpg',
    '.png',
    '.webp',
)


class UploadedFile(ndb.Model):
    blob_key = ndb.StringProperty()
    gs_path = ndb.StringProperty()
    uploaded = ndb.DateTimeProperty(auto_now_add=True)

    @classmethod
    def create_file_id(cls):
        existing = True
        # Ensure ID is unique.
        while existing is not None:
            file_id = str(uuid.uuid4())[:12].replace('-', '')
            existing = ndb.Key('UploadedFile', file_id).get()
        return file_id


class CreateUploadUrlHandler(webapp2.RequestHandler):

    def json_response(self, data, status=200):
        self.response.set_status(status)
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(data))

    def get(self):
        content_length = int(self.request.GET.get('content_length'))
        timestamp = numpy.int64(round(time.time() * 1000000))
        name = self.request.GET.get('name', timestamp).strip('/')
        content_type = mimetypes.guess_type(name)[0]

        if '..' in name or '/' in name:
            self.error(400)
            return

        if FOLDER and FOLDER != 'None':
            gs_path_format = '/{bucket}/{folder}/{timestamp}'
            gs_path = gs_path_format.format(
                bucket=BUCKET_NAME, folder=FOLDER, timestamp=timestamp)
        else:
            gs_path_format = '/{bucket}/{timestamp}'
            gs_path = gs_path_format.format(
                bucket=BUCKET_NAME, timestamp=timestamp)
        gs_path = os.path.join(gs_path, name)

        signer = google_storage_signer.CloudStorageURLSigner()
        request = signer.create_put(gs_path, content_type, content_length)
        upload_url = request['url'] + '?' + urllib.urlencode(request['params'])

        file_id = UploadedFile.create_file_id()
        blob_key = blobstore.create_gs_key('/gs{}'.format(gs_path))
        key = ndb.Key('UploadedFile', file_id)
        ent = UploadedFile(key=key, gs_path=gs_path, blob_key=blob_key)
        ent.put()

        data = {
            'content_type': content_type,
            'upload_url': upload_url,
            'gs_path': gs_path,
            'file_id': file_id,
        }
        self.json_response(data)


class CreateServingUrlHandler(webapp2.RequestHandler):

    def json_response(self, data, status=200):
        self.response.set_status(status)
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(data))

    def post(self):
        file_id = self.request.POST.get('file_id')
        key = ndb.Key('UploadedFile', file_id)
        ent = key.get()
        if ent.gs_path.endswith(IMAGE_EXTENSIONS):
            blob_key = blobstore.create_gs_key('/gs{}'.format(ent.gs_path))
            serving_url = images.get_serving_url(blob_key, secure_url=True)
            data = blobstore.fetch_data(blob_key, 0, 50000)
            image = images.Image(image_data=data)
            ent.width = image.width
            ent.height = image.height
        else:
            serving_url = 'https://storage.googleapis.com{}'.format(ent.gs_path)
            ent.width = 0
            ent.height = 0
        ent.serving_url = serving_url
        ent.put()
        self.json_response({
            'file_id': file_id,
            'gs_path': ent.gs_path,
            'serving_url': serving_url,
            'width': ent.width,
            'height': ent.height,
        })


class ServeFileHandler(webapp2.RequestHandler):

    def get(self, file_id):
        ent = ndb.Key('UploadedFile', file_id).get()
        if not ent:
            self.abort(404)
            return
        if 'Content-Type' in self.response.headers:
            del self.response.headers['Content-Type']
        self.response.headers['X-AppEngine-BlobKey'] = str(ent.blob_key)


app = webapp2.WSGIApplication([
    ('/_api/create_serving_url', CreateServingUrlHandler),
    ('/_api/create_upload_url', CreateUploadUrlHandler),
    ('/(.*)', ServeFileHandler),
])
