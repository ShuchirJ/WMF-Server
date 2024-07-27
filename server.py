print('START VERSION: 13')
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
import requests, json, time
from datetime import datetime
import pytextnow
from dotenv import load_dotenv
import os

load_dotenv()

client = (Client()
    .set_endpoint('https://appwrite.shuchir.dev/v1') # Your API Endpoint
    .set_project('wheresmyflight')                # Your project ID
    .set_key(os.environ['APPWRITE_KEY']))          # Your secret API key
db = Databases(client)

tn = pytextnow.Client("coolcodersj0", sid_cookie=os.environ['TEXTNOW_SID'], csrf_cookie=os.environ['TEXTNOW_CSRF'])

def notify(title, message, flightId):
    message = message.replace("<br/>", "\n")
    print("MESSAGE:", message)

    flight = db.get_document("data", "flights", flightId)
    settings = db.get_document("settings", "prefs", flight['userId'])
    targets = flight['notificationTargets']

    for target in targets:
        if target.startswith("ntfy"):
            base = settings['ntfyBase']
            if not base.endswith("/"): base += "/"
            r = requests.post(f"{base}{target.split(':')[1]}", headers={
                "Priority": "urgent",
                "Title": title,
                "Tags": "airplane"
            }, data=message)
        elif target.startswith("sms"):
            tn.send_sms(target.split(":")[1], message)


requests.get(os.environ['PING_URL'])

def get_all_docs(data, collection, queries=[]):
    docs = []
    offset = 0
    ogq = queries.copy()
    while True:
        queries = ogq.copy()
        queries.append(Query.offset(offset))
        queries.append(Query.limit(100))
        results = db.list_documents(data, collection, queries=queries)
        if len(docs) == results['total']:
            break
        results = results['documents']
        docs += results
        offset += len(results)
    return docs

documents = get_all_docs('data', 'flights')
# print(documents)

def checkBaggage(flightId):
    boardingcard = db.list_documents("data", "passes", queries=[Query.equal("flightId", flightId)])['documents']
    if len(boardingcard) == 0: return
    doneCode = []
    #print(boardingcard)
    for card in boardingcard:
        #print(card)
        code = card['deltacode']
        print("precode", code, "flight", flightId)
        if code in doneCode: continue
        doneCode.append(code)
        print("code", code)
        lastname = card['data'][2:].split("/")[0]
        payload = json.dumps({
        "bagRequestDetails": {
            "requestType": "REC_LOC",
            "recordLocatorId": code,
            "lastName": lastname.title()
        }
        })
        headers = {
        'content-type': 'application/json',
        'Host': 'www.delta.com',
        'User-Agent': 'Python/Requests',
        }
        server_bags = requests.request("POST", "https://www.delta.com/baggage/baggageStatus", headers=headers, data=payload).json()
        print(server_bags)
        server_bags_list = {}
        if "passengerBags" not in server_bags: return
        for passenger in server_bags['passengerBags']:
            for bag in passenger['bags']:
                server_bags_list[bag['bagTagNum']] = {
                    "name": passenger['passenger']['firstName'] + " " + passenger['passenger']['lastName'],
                    "status": []
                }
        
        for bag in server_bags['bagHistoryList']:
            for status in bag['bagStatuses']:
                server_bags_list[bag['bagTagNum']]['status'].append({
                    "airport": status['airportCode'],
                    "time": status['statusDtTm'],
                    "details": status['statusDetails']
                })
        
        print(server_bags_list)
        allbaggage = db.list_documents("data", "bags", queries=[Query.equal("flightId", flightId)])['documents']
        db_bagtags = []
        db_bags = {}
        for bag in allbaggage:
            db_status = json.loads(bag['status'])
            tag = bag['id']
            db_bagtags.append(tag)
            db_bags[tag] = db_status
        
        for bag, data in server_bags_list.items():
            server_status = data['status']
            print("\n\nserver status", server_status, "\n\n")
            for status in server_status:
                if bag in db_bags:
                    if status not in db_bags[bag]:
                        print("Baggage Status Update", f"Baggage {bag} for passenger {data['name']} has been updated. It is now at {status['airport']} with status {status['details']} at {status['time']}.")
                        notify("Baggage Status Update", f"Baggage {bag} for passenger {data['name']} has been updated. It is now at {status['airport']} with status {status['details']} at {status['time']}.", flightId)
                else:
                    print("Baggage Status Update", f"Baggage {bag} for passenger {data['name']} has been updated. It is now at {status['airport']} with status {status['details']} at {status['time']}.")
                    notify("Baggage Status Update", f"Baggage {bag} for passenger {data['name']} has been updated. It is now at {status['airport']} with status {status['details']} at {status['time']}.", flightId)

        for bag, data in server_bags_list.items():
            print("SENDING TO DB:", bag)
            if bag not in db_bagtags:
                db.create_document("data", "bags", "unique()", {
                    "flightId": flightId,
                    "id": bag,
                    "status": json.dumps(data['status']),
                    "name": data['name']
                })
            else:
                db_id = db.list_documents("data", "bags",  queries=[Query.equal("id", bag)])['documents'][0]['$id']
                db.update_document("data", "bags", db_id, {
                    "status": json.dumps(data['status']),
                    "name": data['name']
                })
            print("BAG DONE:", bag)

for db_flight in documents:
    if db_flight['fullData'][18] == "historical": continue
    flightId = db_flight['flightId']
    if flightId.startswith("DL"):
        checkBaggage(flightId)
    
    fuuid = db_flight['$id']

    aircode = db_flight['fullData'][25]
    flightnum = db_flight['fullData'][26]
    print(flightId)
    date = db_flight['fullData'][27]
    yr = date.split("/")[2]
    month = date.split("/")[0]
    day = date.split("/")[1]
    r = requests.get(f"https://www.flightstats.com/v2/api-next/flight-tracker/{aircode}/{flightnum}/{yr}/{month}/{day}/")
    if r.status_code == 200:
        try:
            flight = r.json()['data']
        except Exception as e:
            print(e)
            continue
        # print(flight)
        aircraft = flight['additionalFlightInfo']['equipment']['name']
        airline = flight['ticketHeader']['carrier']['name']

        originTZ = flight['departureAirport']['times']['scheduled']['timezone'];
        originAirport = flight['departureAirport']['iata'] + " (" + flight['departureAirport']['name'] + ")";
        originCity = flight['departureAirport']['city'];
        originGate = flight['departureAirport']['gate'];
        originTerminal = flight['departureAirport']['terminal'];

        destinationTZ = flight['arrivalAirport']['times']['scheduled']['timezone'];
        destinationAirport = flight['arrivalAirport']['iata'] + " (" + flight['arrivalAirport']['name'] + ")";
        destinationCity = flight['arrivalAirport']['city'];
        destinationGate = flight['arrivalAirport']['gate'];
        destinationTerminal = flight['arrivalAirport']['terminal'];

        r2 = requests.get(f"https://www.flightstats.com/v2/api-next/flick/{flight['flightId']}?guid=34b64945a69b9cac:5ae30721:13ca699d305:XXXX&airline={aircode}&flight={flightnum}&flightPlan=true&rqid=0gjukufd01k")
        dist = r2.json()['data']
        try:
            print(dist['miniTracker'])
            print(f"https://www.flightstats.com/v2/api-next/flick/{flight['flightId']}?guid=34b64945a69b9cac:5ae30721:13ca699d305:XXXX&airline={aircode}&flight={flightnum}&flightPlan=true&rqid=0gjukufd01k")
        except: print("no dist")
        try: actualDist = str(round(dist['miniTracker']['totalKilometers'] * 1.151)) + "mi";
        except: actualDist = "--"
        try: plannedDist = str(round(dist['miniTracker']['totalKilometers'] * 1.151)) + "mi";
        except: plannedDist = "--"
        try: takenDist = str(round(dist['miniTracker']['kilometersFromDeparture'] * 1.151)) + "mi";
        except: takenDist = "--"

        try: speed = str(round(flight['positional']['flexTrack']['positions'][0]['speedMph'])) + "mph";
        except: speed = "--"
        try: altitude = str(round(flight['positional']['flexTrack']['positions'][0]['altitudeFt'])) + "ft";
        except: altitude = "--"
        fuel = "--"

        depRun = "--"
        arrRun = "--"
        baggageClaim = ""

        r3 = requests.get(f"https://www.flightstats.com/v2/api/extendedDetails/{aircode}/{flightnum}/{yr}/{month}/{day}/{flight['flightId']}?rqid=t4u711r6ec")
        extended = r3.json()
        try:
            depTimes = extended['departureTimes']
            if "estimatedRunway" in depTimes:
                depRun = f"{depTimes['estimatedRunway']['time']} {depTimes['estimatedRunway']['ampm']} {depTimes['estimatedRunway']['timezone']}"
            elif "actualRunway" in depTimes:
                depRun = f"{depTimes['actualRunway']['time']} {depTimes['actualRunway']['ampm']} {depTimes['actualRunway']['timezone']}"
        except: pass

        try:
            arrTimes = extended['arrivalTimes']
            if "estimatedRunway" in arrTimes:
                arrRun = f"{arrTimes['estimatedRunway']['time']} {arrTimes['estimatedRunway']['ampm']} {arrTimes['estimatedRunway']['timezone']}"
            elif "actualRunway" in arrTimes:
                arrRun = f"{arrTimes['actualRunway']['time']} {arrTimes['actualRunway']['ampm']} {arrTimes['actualRunway']['timezone']}"
        except: pass

        try:
            baggageClaim = extended['arrivalAirport']['baggage']
        except: pass

        status = flight['flightState'];
        print(flight['schedule'])
        try: scheduledDepartureTime = datetime.strptime(flight['schedule']['scheduledDeparture'], "%Y-%m-%dT%H:%M:%S.%f")
        except: scheduledDepartureTime = None
        try: estimatedDepartureTime = datetime.strptime(flight['schedule']['estimatedActualDeparture'], "%Y-%m-%dT%H:%M:%S.%f");
        except: estimatedDepartureTime = None
        try: actualDepartureTime = datetime.strptime(flight['schedule']['estimatedActualDeparture'], "%Y-%m-%dT%H:%M:%S.%f");
        except: actualDepartureTime = None

        try: scheduledArrivalTime = datetime.strptime(flight['schedule']['scheduledArrival'], "%Y-%m-%dT%H:%M:%S.%f");
        except: scheduledArrivalTime = None
        try: estimatedArrivalTime = datetime.strptime(flight['schedule']['estimatedActualArrival'], "%Y-%m-%dT%H:%M:%S.%f");
        except: estimatedArrivalTime = None
        try: actualArrivalTime = datetime.strptime(flight['schedule']['estimateActualArrival'], "%Y-%m-%dT%H:%M:%S.%f");
        except: actualArrivalTime = None

        coordinates = [];
        if flight['positional']['flexTrack']['positions']:
            for i in range(len(flight['positional']['flexTrack']['positions'])):
                coord = [flight['positional']['flexTrack']['positions'][i]['lat'], flight['positional']['flexTrack']['positions'][i]['lon']];
                coordinates.append(coord)

        speedPoints = [];
        if flight['positional']['flexTrack']['positions']:
            for i in range(len(flight['positional']['flexTrack']['positions'])):
                speedPoint = flight['positional']['flexTrack']['positions'][i]['speedMph'];
                speedPoints.append(speedPoint)
        
        altitudePoints = [];
        if flight['positional']['flexTrack']['positions']:
            for i in range(len(flight['positional']['flexTrack']['positions'])):
                altitudePoint = flight['positional']['flexTrack']['positions'][i]['altitudeFt'];
                altitudePoints.append(altitudePoint)

        db_aircraft, db_airline, db_originTZ, db_originAirport, db_originCity, db_originGate, db_originTerminal, db_destinationTZ, db_destinationAirport, db_destinationCity, db_destinationGate, db_destinationTerminal, db_actualDist, db_plannedDist, db_takenDist, db_speed, db_altitude, db_fuel, db_status, db_scheduledDepartureTime, db_estimatedDepartureTime, db_actualDepartureTime, db_scheduledArrivalTime, db_estimatedArrivalTime, db_actualArrivalTime, aircode, flightnum, date = db_flight['fullData']
        db_depRun, db_arrRun = db_flight['runwayTimes']
        db_baggageClaim = db_flight['baggageClaim']

        if db_scheduledDepartureTime and scheduledDepartureTime:
            try: db_scheduledDepartureTime = datetime.strptime(db_scheduledDepartureTime, '%Y-%m-%dT%H:%M:%S.%fZ')
            except: 
                try: db_scheduledDepartureTime = datetime.strptime(db_scheduledDepartureTime, '%Y-%m-%dT%H:%M:%S%Z')
                except: db_scheduledDepartureTime = datetime.strptime(db_scheduledDepartureTime, '%Y-%m-%dT%H:%M:%S')
            scheduledDepartureTime = scheduledDepartureTime.replace(tzinfo=db_scheduledDepartureTime.tzinfo)
        if db_estimatedDepartureTime and estimatedDepartureTime:
            try: db_estimatedDepartureTime = datetime.strptime(db_estimatedDepartureTime, '%Y-%m-%dT%H:%M:%S.%fZ')
            except: 
                try: db_estimatedDepartureTime = datetime.strptime(db_estimatedDepartureTime, '%Y-%m-%dT%H:%M:%SZ')
                except: db_estimatedDepartureTime = datetime.strptime(db_estimatedDepartureTime, '%Y-%m-%dT%H:%M:%S')
            estimatedDepartureTime = estimatedDepartureTime.replace(tzinfo=db_estimatedDepartureTime.tzinfo)
        if db_actualDepartureTime and actualDepartureTime:
            try: db_actualDepartureTime = datetime.strptime(db_actualDepartureTime, '%Y-%m-%dT%H:%M:%S.%fZ')
            except: 
                try: db_actualDepartureTime = datetime.strptime(db_actualDepartureTime, '%Y-%m-%dT%H:%M:%S%Z')
                except: db_actualDepartureTime = datetime.strptime(db_actualDepartureTime, '%Y-%m-%dT%H:%M:%S')
            actualDepartureTime = actualDepartureTime.replace(tzinfo=db_actualDepartureTime.tzinfo)
        if db_scheduledArrivalTime and scheduledArrivalTime:
            try: db_scheduledArrivalTime = datetime.strptime(db_scheduledArrivalTime, '%Y-%m-%dT%H:%M:%S.%fZ')
            except: 
                try: db_scheduledArrivalTime = datetime.strptime(db_scheduledArrivalTime, '%Y-%m-%dT%H:%M:%S%Z')
                except: db_scheduledArrivalTime = datetime.strptime(db_scheduledArrivalTime, '%Y-%m-%dT%H:%M:%S')
            scheduledArrivalTime = scheduledArrivalTime.replace(tzinfo=db_scheduledArrivalTime.tzinfo)
        if db_estimatedArrivalTime and estimatedArrivalTime:
            try: db_estimatedArrivalTime = datetime.strptime(db_estimatedArrivalTime, '%Y-%m-%dT%H:%M:%S.%fZ')
            except: 
                try: db_estimatedArrivalTime = datetime.strptime(db_estimatedArrivalTime, '%Y-%m-%dT%H:%M:%S%Z')
                except: db_estimatedArrivalTime = datetime.strptime(db_estimatedArrivalTime, '%Y-%m-%dT%H:%M:%S')
            estimatedArrivalTime = estimatedArrivalTime.replace(tzinfo=db_estimatedArrivalTime.tzinfo)
        if db_actualArrivalTime and actualArrivalTime:
            try: db_actualArrivalTime = datetime.strptime(db_actualArrivalTime, '%Y-%m-%dT%H:%M:%S.%fZ')
            except: 
                try: db_actualArrivalTime = datetime.strptime(db_actualArrivalTime, '%Y-%m-%dT%H:%M:%S%Z')
                except: db_actualArrivalTime = datetime.strptime(db_actualArrivalTime, '%Y-%m-%dT%H:%M:%S')
            actualArrivalTime = actualArrivalTime.replace(tzinfo=db_actualArrivalTime.tzinfo)

        infstr = f"from {flight['departureAirport']['iata']} to {flight['arrivalAirport']['iata']}"

        if db_originAirport != originAirport:
            continue

        if depRun and db_depRun != depRun:
            notify("Departure Runway Changed", f"{flightId} {infstr} has changed departure runway from {db_depRun} to {depRun}", fuuid)
        if arrRun and db_arrRun != arrRun:
            notify("Arrival Runway Changed", f"{flightId} {infstr} has changed arrival runway from {db_arrRun} to {arrRun}", fuuid) 

        if baggageClaim and db_baggageClaim != baggageClaim:
            notify("Baggage Claim Changed", f"{flightId} {infstr} has changed baggage claim from {db_baggageClaim} to {baggageClaim}", fuuid)

        if aircraft and db_aircraft != aircraft:
            notify("Aircraft Changed", f"{airline} {flightId} {infstr} has changed aircraft from {db_aircraft} to {aircraft}", fuuid)
        if airline and db_airline != airline:
            notify("Airline Changed", f"{flightId} {infstr} has changed airlines from {db_airline} to {airline}", fuuid)
        if originAirport and db_originAirport != originAirport:
            notify("Origin Airport Changed", f"{flightId} {infstr} has changed origin airport from {db_originAirport} to {originAirport}", fuuid)
        if originCity and db_originCity != originCity:
            notify("Origin City Changed", f"{flightId} {infstr} has changed origin city from {db_originCity} to {originCity}", fuuid)
        if originGate and db_originGate != originGate:
            notify("Origin Gate Changed", f"{flightId} {infstr} has changed origin gate from {db_originGate} to {originGate}", fuuid)
        if originTerminal and db_originTerminal != originTerminal:
            notify("Origin Terminal Changed", f"{flightId} {infstr} has changed origin terminal from {db_originTerminal} to {originTerminal}", fuuid)
        if destinationAirport and db_destinationAirport != destinationAirport:
            notify("Destination Airport Changed", f"{flightId} {infstr} has changed destination airport from {db_destinationAirport} to {destinationAirport}", fuuid)
        if destinationCity and db_destinationCity != destinationCity:
            notify("Destination City Changed", f"{flightId} {infstr} has changed destination city from {db_destinationCity} to {destinationCity}", fuuid)
        if destinationGate and db_destinationGate != destinationGate:
            notify("Destination Gate Changed", f"{flightId} {infstr} has changed destination gate from {db_destinationGate} to {destinationGate}", fuuid)
        if destinationTerminal and db_destinationTerminal != destinationTerminal:
            notify("Destination Terminal Changed", f"{flightId} {infstr} has changed destination terminal from {db_destinationTerminal} to {destinationTerminal}", fuuid)
        if estimatedDepartureTime and estimatedDepartureTime != db_estimatedDepartureTime:
            change = ""
            #calculate specific difference between times
            if estimatedDepartureTime and db_scheduledDepartureTime:
                print(estimatedDepartureTime, db_scheduledDepartureTime)
                if estimatedDepartureTime > db_scheduledDepartureTime:
                    change = "delayed"
                else:
                    change = "ahead of schedule"
                amtchange = abs(estimatedDepartureTime - db_scheduledDepartureTime)
                if amtchange.total_seconds() > 0: notify("Estimated Departure Time Changed", f"{flightId} {infstr} has changed estimated departure time from {db_scheduledDepartureTime.strftime('%m/%d/%Y %I:%M:%S %p')} to {estimatedDepartureTime.strftime('%m/%d/%Y %I:%M:%S %p')}. It is {change} by {amtchange}", fuuid)
        
        
        if estimatedArrivalTime and estimatedArrivalTime != db_estimatedArrivalTime:
            change = ""
            #calculate specific difference between times
            if estimatedArrivalTime and db_scheduledArrivalTime:
                if estimatedArrivalTime > db_scheduledArrivalTime:
                    change = "delayed"
                else:
                    change = "ahead of schedule"
                amtchange = abs(estimatedArrivalTime - db_scheduledArrivalTime)
                if amtchange.total_seconds() > 0: notify("Estimated Arrival Time Changed", f"{flightId} {infstr} has changed estimated arrival time from {db_scheduledArrivalTime.strftime('%m/%d/%Y %I:%M:%S %p')} to {estimatedArrivalTime.strftime('%m/%d/%Y %I:%M:%S %p')}. It is {change} by {amtchange}", fuuid)

        print(aircraft, airline, originTZ, originAirport, originCity, originGate, originTerminal, destinationTZ, destinationAirport, destinationCity, destinationGate, destinationTerminal, actualDist, plannedDist, takenDist, speed, altitude, fuel, status, scheduledDepartureTime, estimatedDepartureTime, actualDepartureTime, scheduledArrivalTime, estimatedArrivalTime, actualArrivalTime)

        if scheduledArrivalTime: scheduledArrivalTime = scheduledArrivalTime.isoformat()
        if estimatedArrivalTime: estimatedArrivalTime = estimatedArrivalTime.isoformat()
        if actualArrivalTime: actualArrivalTime = actualArrivalTime.isoformat()
        if scheduledDepartureTime: scheduledDepartureTime = scheduledDepartureTime.isoformat()
        if estimatedDepartureTime: estimatedDepartureTime = estimatedDepartureTime.isoformat()
        if actualDepartureTime: actualDepartureTime = actualDepartureTime.isoformat()


        db.update_document("data", "flights", db_flight['$id'], {
            "airport": [flight['departureAirport']['iata'], flight['arrivalAirport']['iata']],
            "location": [originCity, destinationCity],
            "gate": [originGate, destinationGate],
            "time": [estimatedDepartureTime, estimatedArrivalTime],
            "gate": [originGate, destinationGate],
            "fullData": [aircraft, airline, originTZ, originAirport, originCity, originGate, originTerminal, destinationTZ, destinationAirport, destinationCity, destinationGate, destinationTerminal, actualDist, plannedDist, takenDist, speed, altitude, fuel, status, scheduledDepartureTime, estimatedDepartureTime, actualDepartureTime, scheduledArrivalTime, estimatedArrivalTime, actualArrivalTime, aircode, flightnum, date],
            "coordinates": json.dumps(coordinates),
            "speed": json.dumps(speedPoints),
            "altitude": json.dumps(altitudePoints),
            "runwayTimes": [depRun, arrRun],
            "baggageClaim": baggageClaim
        })
print('END VERSION: 13')
