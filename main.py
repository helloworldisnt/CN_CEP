# main.py
import time, json, dht
from machine import Pin #For ESP configuration
from umqtt.simple import MQTTClient
import urequests as requests

SERVER_IP = "192.168.43.7"  #IP Address


MQTT_BROKER = SERVER_IP
HTTP_URL = "http://" + SERVER_IP + ":5000/sensor-data"
TOPIC = "coldstorage/live"

# Hardware Setup (GPIO 4 = Milk, GPIO 5 = Frozen)
sensor_milk = dht.DHT22(Pin(4))
sensor_frozen = dht.DHT22(Pin(5))

def connect_mqtt():
    try:
        client = MQTTClient("esp32_hotspot_user", MQTT_BROKER)
        client.connect()
        print("Connected to MQTT Broker at", SERVER_IP)
        return client
    except Exception as e:
        print(f"MQTT Connection Failed: {e}")
        return None

print("System Starting...")
time.sleep(2) # For WiFi Stabilization
client = connect_mqtt()

while True:
    try:
        #Read the sensors
        sensor_milk.measure()
        sensor_frozen.measure()
        
        #Prepare time-stamp
        t = time.localtime()
        timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])
        
        data_milk = {
            "unit_id": 1, "unit_name": "Milk Storage",
            "temperature": sensor_milk.temperature(),
            "humidity": sensor_milk.humidity(),
            "timestamp": timestamp
        }
        
        data_frozen = {
            "unit_id": 2, "unit_name": "Frozen Food Storage",
            "temperature": sensor_frozen.temperature(),
            "humidity": sensor_frozen.humidity(),
            "timestamp": timestamp
        }

        #Using MQTT
        if client:
            try:
                client.publish(TOPIC, json.dumps(data_milk))
                client.publish(TOPIC, json.dumps(data_frozen))
                print(f"MQTT Sent: {data_milk['temperature']}C, {data_frozen['temperature']}C")
            except:
                print("MQTT Reconnecting...")
                client = connect_mqtt()

        #HTTP Logging
        try:
            requests.post(HTTP_URL, json=data_milk).close()
            requests.post(HTTP_URL, json=data_frozen).close()
            print("HTTP Logged")
        except:
            print("HTTP Failed (Is Server Running?)")

    except OSError:
        print("Sensor Error: Check Wiring (3V3/GND/D4/D5)")
    except Exception as e:
        print(f"Error: {e}")

    time.sleep(2)