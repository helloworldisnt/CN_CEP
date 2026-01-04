import pymysql
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import paho.mqtt.client as mqtt

app = Flask(__name__)
CORS(app)

#Configring MySQL
DB_CONFIG = {
    "host": "localhost",
    "user": "admin",
    "password": "password123", 
    "database": "cold_storage_db",
    "cursorclass": pymysql.cursors.Cursor 
}


latest_mqtt_data = {}       # Live data per unit
alert_history = []          # List to store alert logs
last_alert_time = {1: 0, 2: 0} # To prevent spamming alerts

#Function to Initialize the Databse
def init_db():
    conn = pymysql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    cursor = conn.cursor()
    
    cursor.execute("CREATE DATABASE IF NOT EXISTS cold_storage_db") #Create Database
    
    cursor.execute("USE cold_storage_db") #Use the database
    
    # Create table for sensor readings
    #Create table for storage units
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS StorageUnits (
    unit_id INT PRIMARY KEY,
    unit_name VARCHAR(50),
    min_temp DECIMAL(5,2),
    max_temp DECIMAL(5,2)
);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            unit_id INT,
            unit_name VARCHAR(255),
            temperature FLOAT,
            humidity FLOAT,
            timestamp VARCHAR(255),
            FOREIGN KEY (unit_id) REFERENCES StorageUnits(unit_id)
        )
    """)

    conn.commit()
    conn.close()
    print("MySQL Database 'cold_storage_db' and Table 'sensor_readings' ready.")


init_db() #Initialize the database


def process_event(data):
    global alert_history, last_alert_time

    unit_id = data["unit_id"]
    temp = data["temperature"]
    current_time = time.time()
    
    # Update live data
    latest_mqtt_data[unit_id] = data

    # Generate alert messages
    alert_msg = None
    if unit_id == 1 and temp > 5.0:
        alert_msg = f"Critical: Milk Storage High Temp ({temp}°C)"
    elif unit_id == 2 and temp > -5.0:
        alert_msg = f"Critical: Frozen Food Thawing ({temp}°C)"

    # Log only after 60s of last alert - to prevent spamming
    if alert_msg:
        if (current_time - last_alert_time.get(unit_id, 0)) > 60:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = {"time": timestamp, "message": alert_msg, "unit": unit_id}
            
            
            alert_history.insert(0, log_entry) #Add to history
            if len(alert_history) > 50: alert_history.pop() #Pop if entries are more than 50
            
            last_alert_time[unit_id] = current_time
            print(f"ALERT LOGGED: {alert_msg}")

#Note: MQTT Handling - Using Mosquitto as the client
def on_mqtt_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        process_event(data)
    except Exception as e:
        print(f"MQTT Error: {e}")

def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect("localhost", 1883, 60)
        client.subscribe("coldstorage/live")
        client.on_message = on_mqtt_message
        client.loop_forever()
    except Exception as e:
        print(f"Could not connect to Mosquitto: {e}")
        print("Make sure Mosquitto is installed and running!")

#Using Flask for website
@app.route("/")
def index():
    return render_template("index.html")

#For Graphing
@app.route("/sensor-data", methods=["POST"])
def receive_data():
    data = request.json
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        sql = "INSERT INTO sensor_readings (unit_id, unit_name, temperature, humidity, timestamp) VALUES (%s, %s, %s, %s, %s)"
        val = (data["unit_id"], data["unit_name"], data["temperature"], data["humidity"], data["timestamp"])
        
        cursor.execute(sql, val)
        conn.commit()
        conn.close()
        return jsonify({"status": "saved"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Graph History
@app.route("/history", methods=["GET"])
def history():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Fetching last 20 readings
        cursor.execute("SELECT unit_id, unit_name, temperature, humidity, timestamp FROM sensor_readings ORDER BY id DESC LIMIT 20")
        rows = cursor.fetchall()
        conn.close()
        
        result = [{"unit_id": r[0], "temperature": r[2], "humidity": r[3], "timestamp": r[4]} for r in rows]
        
        return jsonify(result), 200
    except Exception as e:
        print(f"DB Error: {e}")
        return jsonify([]), 500

# For live data and alerts
@app.route("/live", methods=["GET"])
def live():
    return jsonify({
        "latest_data": latest_mqtt_data,
        "alerts": alert_history
    })

if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    app.run(host="0.0.0.0", port=5000, debug=True)