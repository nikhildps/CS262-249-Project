from bottle import get, HTTPResponse, post, request, run
from contextlib import closing

import httplib
import json
import socket # Only for inet_aton
import time

LISTEN_PORT = 8080
ACTUATOR_PORT = 80
THRESHOLD_LOW = 0
THRESHOLD_HIGH = 128

# Global variables might not be the best idea
# Just using them to get this done quickly for the project demo
# No need for mutexes because Bottle's dev server is single-threaded
actuatorIpAddrs = set([])
sensorReadings = {}

def sendActuationSignals(ip_addrs):
    headers = {"Content-type", "application/json"}
    request_data = {"Signal" : "Red"}
    for addr in ip_addrs:
        with closing(httplib.HTTPConnection(addr)) as conn:
            # time.time() should return a float with msec precision
            current_time_millis = int(round(time.time() * 1000))
            request_data["Time"] = current_time_millis
            request_body = json.dumps(request_data, sort_keys=True)
            conn.request("POST", "/", request_body, headers)

@post('/actuators')
def register_actuator():
    request_data = request.json

    if request_data is None:
        return HTTPResponse(status=400, body="Request body must be valid JSON")

    ip_addr = request_data.get("IP")
    try:
        socket.inet_aton(ip_addr) # Quick & dirty way to validate an IP address
    except socket.error:
        return HTTPResponse(status=400, body="Improperly formatted IP address")
    actuatorIpAddrs.add(ip_addr)
    return HTTPResponse(status=201, body="Actuator registered")

@post('/sensor_data')
def add_sensor_data():
    request_data = request.json
    print 

    if request_data is None:
        return HTTPResponse(status=400, body="Request body must be valid JSON")

    uuid = request_data.get("UUID")
    if uuid is None:
        return HTTPResponse(status=400, body="Request body must contain UUID")
    temperature = request_data.get("Temperature")
    if temperature is None:
        return HTTPResponse(status=400, body="Request body must contain temperature")
    try:
        temperature = float(temperature)
    except ValueError:
        return HTTPResponse(status=400, body="Request body contained invalid temperature")
    sensorReadings[uuid] = temperature

    if min(sensorReadings.itervalues()) < THRESHOLD_LOW:
        relevant_addrs = [addr for (i,addr) in enumerate(actuatorIpAddrs) if i % 2 == 0]
        sendActuationSignals(relevant_addrs)
    if max(sensorReadings.itervalues()) > THRESHOLD_HIGH:
        relevant_addrs = [addr for (i,addr) in enumerate(actuatorIpAddrs) if i % 2 == 1]
        sendActuationSignals(relevant_addrs)

    return HTTPResponse(status=201, body="Sensor value received successfully")

if __name__ == '__main__':
    run(host='localhost', port=LISTEN_PORT)
