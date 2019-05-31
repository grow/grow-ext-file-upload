from google.appengine.ext import vendor
vendor.add('lib')

from google.appengine.api import app_identity
from google.appengine.api import images
from google.appengine.ext import blobstore
from google.appengine.ext import ndb
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp import template
import cloudstorage as gcs
import json
import logging
import os
import webapp2


APPID = app_identity.get_application_id()
BUCKET_NAME = app_identity.get_default_gcs_bucket_name()
FOLDER = 'grow-ext-cloud-images-uploads'

gcs.set_default_retry_params(
    gcs.RetryParams(initial_delay=0.2,
                    max_delay=5.0,
                    backoff_factor=2,
                    max_retry_period=15))


# TODO: Log uploaded images so they can be reset/deleted by path later.
class UploadedImage(ndb.Model):
    path = ndb.StringProperty(repeated=True)



class UploadCallbackHandler(blobstore_handlers.BlobstoreUploadHandler):

    def post(self):
        uploaded_files = self.get_uploads('file')
        blob_info = uploaded_files[0]
        blob_key = blob_info.key()
        url = images.get_serving_url(blob_key, secure_url=True)
        self.redirect(url)


class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):

    def get(self, bucket=None):
        bucket = bucket or BUCKET_NAME
        gs_bucket_name = '{}/{}'.format(bucket, FOLDER)
        action = blobstore.create_upload_url(
                '/callback', gs_bucket_name=gs_bucket_name)
        kwargs = {
            'bucket': gs_bucket_name,
            'action': action,
        }
        self.response.out.write(template.render('upload.html', kwargs))


class GetServingUrlHandler(webapp2.RequestHandler):

    def normalize_gs_path(self, gs_path, locale):
        stat_result = None
        gs_path = '/gs/{}'.format(gs_path.lstrip('/'))
        if '{locale}' not in gs_path:
            stat_result = gcs.stat(gs_path[3:])
            return gs_path, stat_result
	# Retrieve a localized image if it exists, otherwise strip the locale
        # placeholder from the path and return the base image.
        localized_gs_path = gs_path.replace('{locale}', locale)
	try:
            stat_result = gcs.stat(localized_gs_path[3:])
            return localized_gs_path, stat_result
	except (gcs.NotFoundError, gcs.ForbiddenError):
            # If no file exists for the full locale identifier (language and
            # territory), attempt retrieving a file for just the territory.
            if '_' in locale:
                language, territory = locale.split('_', 1)
                localized_gs_path = \
                        gs_path.replace('{locale}', '_{}'.format(territory))
                try:
                    stat_result = gcs.stat(localized_gs_path[3:])
                    return localized_gs_path, stat_result
                except (gcs.NotFoundError, gcs.ForbiddenError):
                    pass
        gs_path = gs_path.replace('@{locale}', '')
        stat_result = gcs.stat(gs_path[3:])
        return gs_path, stat_result

    def get(self, gs_path):
        gs_path = self.request.get('gs_path') or gs_path
        reset_cache = self.request.get('reset_cache')
        locale = self.request.get('locale')
        service_account_email = \
            '{}@appspot.gserviceaccount.com'.format(APPID)
        if not gs_path:
            detail = (
                'Usage: Share GCS objects with `{}`. Make requests to:'
                ' {}://{}/<bucket>/<path>.ext'.format(
                    service_account_email,
                    os.getenv('wsgi.url_scheme'),
                    os.getenv('HTTP_HOST')))
            self.abort(400, detail=detail)
            return
        gs_path, stat_result = self.normalize_gs_path(gs_path, locale)

        # Video handling.
        if stat_result.content_type.startswith('video'):
            video_metadata = {}
            bucket_path = gs_path[3:]  # bucket/path
            if bucket_path.endswith('.mp4'):
                bucket = bucket_path.lstrip('/').split('/')[0]  # bucket
                clean_etag = stat_result.etag.replace('"', '').replace("'", '')
                blob_bucket_path = '/{}/blobs/{}.mp4'.format(bucket, clean_etag)
                try:
                    stat_result = gcs.stat(blob_bucket_path)
                    # Use the blob_bucket_path to support obfuscated mp4 files.
                    bucket_path = blob_bucket_path
                except (gcs.NotFoundError, gcs.ForbiddenError):
                    pass
            url = 'https://storage.googleapis.com{}'.format(bucket_path)
            response_content = json.dumps({
                'content_type': stat_result.content_type,
                'created': stat_result.st_ctime,
                'etag': stat_result.etag,
                'image_metadata': video_metadata,
                'metadata': stat_result.metadata,
                'size': stat_result.st_size,
                'url': url,
            })
        # Image-handling.
        else:
            blob_key = blobstore.create_gs_key(gs_path)
            if reset_cache:
                try:
                    images.delete_serving_url(blob_key)
                except images.Error as e:
                    logging.error('Error deleting {} -> {}'.format(gs_path, str(e)))
            try:
                url = images.get_serving_url(blob_key, secure_url=True)
            except images.AccessDeniedError:
                detail = (
                    'Ensure the following service'
                    ' account has access to the object in Google Cloud Storage:'
                    ' {}'.format(service_account_email))
                self.abort(400, explanation='AccessDeniedError', detail=detail)
                return
            except images.ObjectNotFoundError:
                detail = (
                    'The object was not found. Ensure the following service'
                    ' account has access to the object in Google Cloud Storage:'
                    ' {}'.format(service_account_email))
                self.abort(400, explanation='ObjectNotFoundError', detail=detail)
                return
            except (images.TransformationError, ValueError):
                logging.exception('Debugging TransformationError.')
                detail = (
                    'There was a problem transforming the image. Ensure the'
                    ' following service account has access to the object in Google'
                    ' Cloud Storage: {}'.format(service_account_email))
                self.abort(400, explanation='TransformationError', detail=detail)
                return
            image_metadata = {}
            try:
                data = blobstore.fetch_data(blob_key, 0, 50000)
                image = images.Image(image_data=data)
                image_metadata = {
                        'height': image.height,
                        'width': image.width,
                }
            except images.BadImageError:
                # If the header containing sizes isn't in the first 50000 bytes of the image.
                # Or, if the file uploaded was just not a real image.
                logging.exception('Failed to transform image.')
            response_content = json.dumps({
                'content_type': stat_result.content_type,
                'created': stat_result.st_ctime,
                'etag': stat_result.etag,
                'image_metadata': image_metadata,
                'metadata': stat_result.metadata,
                'size': stat_result.st_size,
                'url': url,
            })

        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(response_content)


app = webapp2.WSGIApplication([
  ('/callback', UploadCallbackHandler),
  ('/upload/(.*)', UploadHandler),
  ('/upload', UploadHandler),
  ('/(.*)', GetServingUrlHandler),
])
