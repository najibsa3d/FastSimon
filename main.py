from flask import Flask, render_template, request
from google.auth.transport import requests
from google.cloud import datastore
import google.oauth2.id_token
import datetime

datastore_client = datastore.Client()
client = datastore.Client()
firebase_request_adapter = requests.Request()

app = Flask(__name__)
history = []
time = -1

def store_time(email, dt):
    entity = datastore.Entity(key=datastore_client.key("User", email, "visit"))
    entity.update({"timestamp": dt})

    datastore_client.put(entity)


def fetch_times(email, limit):
    ancestor = datastore_client.key("User", email)
    query = datastore_client.query(kind="visit", ancestor=ancestor)
    query.order = ["-timestamp"]

    times = query.fetch(limit=limit)

    return times

def get_entity(key):
    key = client.key("Variable", key)
    return client.get(key)

def save_entity(key, value):
    entity = datastore.Entity(client.key("Variable", key))
    entity["value"] = value
    client.put(entity)

def delete_entity(key):
    key = client.key("Variable", key)
    client.delete(key)

def print_info():
    global time
    global history
    print("********************")
    print("time", time)
    for h in history:
        print(h["operation"], h["key"], h["old_value"])
    print("********************")

# Save history for undo
def save_history(operation, key, old_value):
    # print("adding:", f"{operation}, {key}, {old_value}")
    global time
    global history
    time += 1
    history = history[:time]
    history.append({"operation": operation, "key": key, "old_value": old_value})
    print_info()

# Save redo action
def save_redo(operation, key, value):
    redo = datastore.Entity(client.key("RedoStack"))
    redo.update({"operation": operation, "key": key, "value": value})
    client.put(redo)


@app.route("/set", methods=["GET"])
def set_value():
    key = request.args.get("key")
    value = request.args.get("value")

    old_entity = get_entity(key)
    old_value = old_entity["value"] if old_entity else None

    save_entity(key, value)
    save_history("set", key, old_value)

    return {"message": f"{key} = {value}, was = {old_value}"}

@app.route("/get", methods=["GET"])
def get_value():
    key = request.args.get("key")
    entity = get_entity(key)
    print_info()
    return {"value": entity["value"] if entity else "None"}

@app.route("/unset", methods=["GET"])
def unset_value():
    key = request.args.get("key")
    entity = get_entity(key)
    if entity:
        old_value = entity["value"]
        delete_entity(key)
        save_history("unset", key, old_value)
        return {"message": f"{key} None"}
    return {"message": f"{key} not found"}

@app.route("/numequalto", methods=["GET"])
def num_equal_to():
    value = request.args.get("value")
    query = client.query(kind="Variable")
    query.add_filter("value", "=", value)
    count = len(list(query.fetch()))
    return {"count": count}

@app.route("/undo", methods=["GET"])
def undo():
    global time
    global history
    if time < 0:
        return {"message": "Nothing to undo"}
    
    operation = history[time]["operation"]
    key = history[time]["key"]
    old_value = history[time]["old_value"]

    
    current_entity = get_entity(key)
    current_value = current_entity["value"] if current_entity else None
    history[time]["old_value"] = current_value
    save_entity(key, old_value)
    time -= 1
    # print_info()
    return {"message": f"Undo: {operation} {key}"}

@app.route("/redo", methods=["GET"])
def redo():
    global time
    global history
    if time == len(history) - 1:
        return {"message": "nothing to redo"}
    
    time += 1
    operation = history[time]["operation"]
    key = history[time]["key"]
    old_value = history[time]["old_value"]

    current_entity = get_entity(key)
    current_value = current_entity["value"] if current_entity else None
    history[time]["old_value"] = current_value
    save_entity(key, old_value)

    # print_info()
    return {"message": f"Undo: {operation} {key}"}
@app.route("/end", methods=["GET"])
def end():
    print("ending")
    global time
    global history
    time = -1
    history = []
    for kind in ["Variable", "History", "RedoStack"]:
        query = client.query(kind=kind)
        keys = [entity.key for entity in query.fetch()]
        client.delete_multi(keys)

    return {"message": "CLEANED"}


@app.route("/")
def root():
    # Verify Firebase auth.
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    print("ana hons", id_token)
    if id_token:
        try:
            # Verify the token against the Firebase Auth API. This example
            # verifies the token on each page load. For improved performance,
            # some applications may wish to cache results in an encrypted
            # session store (see for instance
            # http://flask.pocoo.org/docs/1.0/quickstart/#sessions).
            claims = google.oauth2.id_token.verify_firebase_token(
                id_token, firebase_request_adapter
            )
            print("*** claims", claims)

            store_time(claims["email"], datetime.datetime.now(tz=datetime.timezone.utc))
            times = fetch_times(claims["email"], 10)

        except ValueError as exc:
            # This will be raised if the token is expired or any other
            # verification checks fail.
            error_message = str(exc)
    else:
        print("no token")
    return render_template(
        "index.html", user_data=claims, error_message=error_message, times=times
    )

if __name__ == "__main__":
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.
    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)