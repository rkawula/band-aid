# Band App

## Installation

You'll need the version of python in the .python-version file. I suggest using pyenv and virtualenv to manage your executable and libraries:

1. Install pyenv for your system (depending on your method, this may come bundled with virtualenv)
2. `pyenv install 3.10.1`
3. `pip install -r requirements.txt`

## Run the app

1. `uvicorn main:app --reload`

## Starting Docker

1.  cd to root project folder
2. `docker build . -t mysql`
3. `docker run -d -p 3306:3306 --name mysql -e MYSQL_PASSWORD=<Replace Me!> mysql`

## Send a request to the API

1. Example: `curl -H "Content-Type: application/json" localhost:8000/band -X POST -d '{"name": "a name", "admin": "me", "location": "somewhere"}'`
