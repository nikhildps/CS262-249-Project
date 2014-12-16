from bottle import get, HTTPResponse, post, request, run
from contextlib import closing
from Queue import Queue
from threading import Thread

import copy
import httplib
import json
import re
import socket # Only for inet_aton
import time

LISTEN_PORT = 8080
ACTUATOR_PORT = 80
LOG_FILE_NAME = "sensor_log.txt"

HEAT_POINT_2 = 14
HEAT_POINT_1 = 16
COOL_POINT_1 = 18
COOL_POINT_2 = 20

COOL_HIGH_SIGNAL = -2
COOL_LOW_SIGNAL = -1
OFF_SIGNAL = 0
HEAT_LOW_SIGNAL = 1
HEAT_HIGH_SIGNAL = 2

OPEN_FULL_SIGNAL = 2
OPEN_PARTIAL_SIGNAL = 1
CLOSED_SIGNAL = 0

# Global variables might not be the best idea
# Just using them to get this done quickly for the project demo
actuator_registry = {}
analysis_queue = Queue() # Queue handles blocking and thread safety

def getCurrentTime():
    t = time.localtime()
    timestamp = {
        "Year" : t.tm_year % 100,
        "Month" : t.tm_mon,
        "Day" : t.tm_mday,
        "Hour" : t.tm_hour,
        "Minute" : t.tm_min,
        "Second" : t.tm_sec
    }
    return timestamp

def sendActuationSignal(ip_addr, signal):
    headers = {"Content-type" : "application/json"}
    request_data = {"Signal" : signal}

    try:
        with closing(httplib.HTTPConnection(ip_addr)) as conn:
            print "Sending to " + ip_addr
            request_data.update(getCurrentTime())
            request_body = json.dumps(request_data, sort_keys=True)
            conn.request("POST", "/", request_body, headers)
            print "Sent to " + ip_addr
    except:
        pass

# This is run by the sensor analysis thread
def analyzeSensorData():
    while True:
        reading, addrs = analysis_queue.get()

        name = reading["Name"]
        hvac_addr = addrs.get("HVAC")
        econ_addr = addrs.get("Economizer")
        if hvac_addr is not None and name == "Room":
            room_temp = float(reading["Temperature"])
            if room_temp > COOL_POINT_2:
                sendActuationSignal(hvac_addr, COOL_HIGH_SIGNAL)
            elif room_temp > COOL_POINT_1:
                sendActuationSignal(hvac_addr, COOL_LOW_SIGNAL)
            elif room_temp < HEAT_POINT_2:
                sendActuationSignal(hvac_addr, HEAT_HIGH_SIGNAL)
            elif room_temp < HEAT_POINT_1:
                sendActuationSignal(hvac_addr, HEAT_LOW_SIGNAL)
            else:
                sendActuationSignal(hvac_addr, OFF_SIGNAL)

        elif econ_addr is not None and name == "Environment":
            env_temp = float(reading["Temperature"])
            if env_temp > COOL_POINT_2 or env_temp < HEAT_POINT_2:
                sendActuationSignal(econ_addr, CLOSED_SIGNAL)
            elif HEAT_POINT_1 < env_temp < COOL_POINT_1:
                sendActuationSignal(econ_addr, OPEN_FULL_SIGNAL)
                if hvac_addr is not None:
                    sendActuationSignal(hvac_addr, "Off")
            else:
                sendActuationSignal(econ_addr, OPEN_PARTIAL_SIGNAL)

def logSensorData(data):
    timestamp = getCurrentTime()
    data["ControllerDate"] = "{}/{}/{}".format(timestamp["Year"], timestamp["Month"], timestamp["Day"])
    data["ControllerTime"] = "{}:{}:{}".format(timestamp["Hour"], timestamp["Minute"], timestamp["Second"])
    with open(LOG_FILE_NAME, "a") as f:
        f.write(json.dumps(data, sort_keys=True))

@post('/actuators')
def registerActuator():
    global acuator_registry
    try:
        request_data = request.json
    except ValueError:
        return HTTPResponse(status=400, body="Request body must be valid JSON")

    if request_data is None:
        return HTTPResponse(status=400, body="Request body must be valid JSON")

    ip_addr = request_data.get("IP")
    if ip_addr is None:
        return HTTPResponse(status=400, body="Request body must contain IP address")
    try:
        socket.inet_aton(ip_addr) # Quick & dirty way to validate an IP address
    except socket.error:
        return HTTPResponse(status=400, body="Improperly formatted IP address")
    name = request_data.get("Name")
    if name is None:
        return HTTPReponse(status=400, body="Request body must contain name")

    actuator_registry[name] = ip_addr
    header = {"Content-Type" : "application/json"}
    timestamp = getCurrentTime()
    return HTTPResponse(status=201, body=json.dumps(timestamp), headers=header)

@post('/sensor_data')
def addSensorData():
    try:
        request_data = request.json
    except ValueError:
        return HTTPResponse(status=400, body="Request body must be valid JSON")

    if request_data is None:
        return HTTPResponse(status=400, body="Request body must be valid JSON")

    temperature = request_data.get("Temperature")
    if temperature is None:
        return HTTPResponse(status=400, body="Request body must contain temperature")
    try:
        temperature = float(temperature)
    except ValueError:
        return HTTPResponse(status=400, body="Request body contained invalid temperature")

    name = request_data.get("Name")
    if name is None:
        return HTTPResponse(status=400, body="Request body must contain name")
    uuid = request_data.get("UUID")
    if uuid is None:
        return HTTPResponse(status=400, body="Request body must contain UUID")
    elif re.match(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', uuid) is None:
        return HTTPResponse(status=400, body="Request body contained invalid UUID")

    logSensorData(request_data)
    analysis_queue.put((request_data, copy.deepcopy(actuator_registry)))
    header = {"Content-Type" : "application/json"}
    timestamp = getCurrentTime()
    return HTTPResponse(status=201, body=json.dumps(timestamp), headers=header)

if __name__ == '__main__':
    analysis_thread = Thread(target=analyzeSensorData)
    analysis_thread.daemon = True
    analysis_thread.start()

    run(host='0.0.0.0', port=LISTEN_PORT)
