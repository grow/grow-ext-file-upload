project :=
version := auto
bucket := $(project).appspot.com

cors:
	gsutil cors set cors-policy.json gs://$(bucket)

run:
	dev_appserver.py app.yaml

deploy:
	gcloud app deploy \
		-q \
		--project=$(project) \
		--version=$(version) \
		--promote \
		app.yaml
