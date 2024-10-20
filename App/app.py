from flask import Flask, render_template, redirect, url_for, session, request, flash, jsonify
import firebase_admin
from flask_session import Session
from firebase_admin import credentials, auth, firestore
import json
import requests
from datetime import timedelta , date, datetime
import user_agents
import time
from db import * 

app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config['SESSION_TYPE'] = 'filesystem'  # You can also use 'redis' or 'sqlalchemy'
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
Session(app)  # Initialize the Flask-Session extension

app.secret_key = f"{time.time()}"  # Change this to a random secret key

app.permanent_session_lifetime = timedelta(days=30)
# Initialize Firebase Admin SDK
cred = credentials.Certificate("App\serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

userDb = db.collection("Users")
purchDb = db.collection("Purchase")
infoDb =  db.collection("Info")
sareDb =  db.collection("Saree")
billsDb = db.collection("bills")

sidebar_items = {
    "top" : [
        {"url": "index", "icon": "home", "text": "Dashboard"},
        {"url": "Inventory", "icon": "storefront", "text": "Inventory"},
        {"url": "Billing", "icon": "point_of_sale", "text": "Billing"}
    ],
    "bottom":[
        {"url": "Setting", "icon": "settings", "text": "Setting"},
        {"url": "logout", "icon": "logout", "text": "Logout"}
    ]
}

data = {
    'sidebar_items' : sidebar_items,
}

def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__  # Preserve the name of the original function
    return wrapper

@app.route("/")
@login_required
def index():
    return render_template("Dashboard.html",data=data,  session=session)

@app.route("/Inventory")
@login_required
def Inventory():
    return render_template("Inventory.html",data=data,  session=session)

@app.route("/Billing")
@login_required
def Billing():
    return render_template("Billing.html",data=data, session=session)

@app.route("/Setting")
@login_required
def Setting():
    return render_template("Setting.html", data=data, session=session)

@app.route("/login", methods=["GET", "POST"])
def login():
    ua_string = request.headers.get('User-Agent')
    user_agent = user_agents.parse(ua_string)

    if user_agent.is_mobile:
        device = 'Mobile'
    else:
        device = 'Desktop'
    
    browser = user_agent.browser.family
    os = user_agent.os.family
    if request.method == "POST":
        # Handle email/password sign-in only
        with open("App/api.json", "r") as f:
            api = json.load(f)
        payload = {
            "email": request.form['email'],
            "password": request.form['password'],
            "returnSecureToken": True
        }
        try:
            user = auth.get_user_by_email(payload["email"]) 
            # Verify password here using a secure method (Firebase client SDK would typically handle this)
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api['Firebase']}"
            response = requests.post(url, json=payload)
            result = response.json()
            if 'localId' in result:
                # Save device info in session
                session['user_id'] = user.uid
                session['name'] = user.display_name
                print(session['name'])
                session['device'] = device
                session['browser'] = browser
                session['os'] = os
                if request.form.get("session"):
                    flash("Checked Rember me")
                    session.permanent = True
                else:
                    flash("Not Checked Rember me")
                    session.permanent = False
            else:
                raise Exception
            return redirect(url_for('index'))
        except Exception as e:
            flash(e)
            flash("Invalid email or password.")
    return render_template("login.html", data=data)

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']
        name = request.form['name']
        phone = "+91"+request.form['phone']
        try:
            user = auth.create_user(email=email, password=password,display_name = name,
                                    phone_number = phone,email_verified = False,
                                    disabled = False)
            data = {
                "name" : name,
                "phone" : phone,
                "email": email,
                "Authority" : 3,
                "ProfileImage":""
            }
            userDb.document(user.uid).set(data)
            flash("Account created successfully!")
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"Error creating account: {e}")
    return render_template("signup.html")


@app.route("/AddSaree_info", methods=['GET', 'POST'])
@login_required
def AddSaree_info():
    if request.method == "POST":
        purchId = str(len(purchDb.get()) + 1)
        purchData = {
            'purchdate': str(date.today()),
            'source': request.form.get('Source'),
            'quantity': request.form.get('Quantity'),
            'userId': session['user_id']
        }
        session['purchId'] = purchId
        sarees = []
        start_number = len(sareDb.get())
        for a in range(int(purchData["quantity"])):
            sareesl = {
                'sareeId': str(start_number + a),
                'Category': request.form.get('Cateogry'),
                'price': request.form.get('Price'),
                'color': '',
                'Images': {
                    "Overview": "",
                    "Fullview": "",
                    "Pallu": "",
                    "Border": ""
                }
            }
            sarees.append(sareesl)

        # Store sarees and purchData in session to be used after redirection
        session['purchData'] = purchData
        session['sarees'] = sarees

        # Redirect to prevent form resubmission on refresh
        return redirect(url_for('AddSaree'))

    return render_template('AddSaree_info.html', data=data, session=session)

@app.route("/AddSaree", methods=["POST", "GET"])
@login_required
def AddSaree():
    # Retrieve the stored data from the session
    purchData = session.pop('purchData', None)
    sarees = session.pop('sarees', None)

    if not purchData or not sarees:
        return redirect(url_for('AddSaree_info'))  # If no data, redirect back to form

    # Store back to session to persist during form submission
    session['purchData'] = purchData
    session['sarees'] = sarees

    if request.method == 'POST':
        # Save purchase data in the 'purchDb' collection
        purchDb.document(document_id=session['purchId']).set(session['purchData'])
        
        # Save each saree's data in the 'sareDb' collection
        for saree in sarees:
            sareeId = saree['sareeId']
            sareDb.document(sareeId).set(saree)  # Storing saree details in Firebase
        
        # Clear session after saving to Firebase to avoid duplicate data on refresh
        session.pop('purchData', None)
        session.pop('sarees', None)
        
        return redirect(url_for('AddSaree'))  # Redirect after successful submission

    return render_template('AddSaree.html', data=data, session=session)


@app.route('/camera')
def camera():
    saree_name = request.args.get('sareeId')  # Get sareeId from query parameters
    if saree_name:
        # You can process the saree_name if needed, e.g., fetch data from a database
        saree_Id, image = saree_name.split('-')
        print(f"Saree Name: {saree_name}")  # For debugging or logging purposes
        
        # session['sarees']
        for a in session['sarees']:
            if saree_Id == str(a['sareeId']):
                a['Images'][image] = saree_name                 
                print(f"\n\n\n\n\n\n\n\n{a}\n\n\n\n\n\n\n\n")

    else:
        saree_name = "default"  # Handle the case where sareeId is not provided
    # Render the camera template and pass the saree_name to it
    return render_template('camera.html', sareeId=saree_name)  # Ensure you have a camera.html template


@app.route("/getSareePrice")
@login_required
def getSareePrice():
    sareeId = request.args.get('sareeId')

    # Retrieve saree from Firebase by sareeId
    saree_ref = sareDb.document(sareeId).get()
    if saree_ref.exists:
        saree_data = saree_ref.to_dict()
        return jsonify({'price': saree_data.get('price')})
    else:
        return jsonify({'price': None})


@app.route("/submit_billing", methods=['POST'])
@login_required
def submit_billing():
    # Get form data
    saree_ids = request.form.getlist('sareeId')
    costs = request.form.getlist('cost')
    address = request.form['address']

    # Process the billing details, e.g., save to database
    billing_data = {
        'saree_details': [{'sareeId': saree_id, 'cost': cost} for saree_id, cost in zip(saree_ids, costs)],
        'address': address,
        'userId': session['user_id'],
        'date': str(date.today())
    }

    # Save billing_data to Firestore or your database
    billsDb.add(billing_data)

    flash("Billing submitted successfully!")
    return redirect(url_for('Billing'))  # Redirect back to the billing page or wherever needed

if __name__ == "__main__":
    app.run(debug=True , port=8080)
    # app.run(debug=True,host='11.12.8.84',port='8080')    