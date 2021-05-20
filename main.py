from boot import MAIN_FILE_LOGGING, MAIN_FILE_MODE, MAIN_FILE_NAME, MAIN_FILE_OW, CPUFREQ, logfiles, rtc # Can remove for final code. Helps with python intellisense (syntax highlighting)
import utime, uos, ubinascii, micropython, network, re, ujson, ulogging
from timer import Timer, TimerFunc
from mytools import pcolor, rtcdate, localdate
from machine import Pin, ADC, PWM, RTC
from lib.umqttsimple import MQTTClient
from upyDCmotor import DCMotor
from encoder import Encoder
import machine
import gc
gc.collect()
micropython.alloc_emergency_exception_buf(100)

def connect_wifi(WIFI_SSID, WIFI_PASSWORD):
    station = network.WLAN(network.STA_IF)

    station.active(True)
    station.connect(WIFI_SSID, WIFI_PASSWORD)

    while station.isconnected() == False:
        pass

    main_logger.info('Connection successful')
    main_logger.info(station.ifconfig())

def mqtt_setup(IPaddress):
    global MQTT_CLIENT_ID, MQTT_SERVER, MQTT_USER, MQTT_PASSWORD, MQTT_SUB_TOPIC, MQTT_REGEX, MQTT_PUB_LVL1, MQTT_SUB_LVL1, ESPID
    with open("stem", "r") as f:    # Remove and over-ride MQTT/WIFI login info below
      stem = f.read().splitlines()
    MQTT_SERVER = IPaddress   # Over ride with MQTT/WIFI info
    MQTT_USER = stem[0]         
    MQTT_PASSWORD = stem[1]
    WIFI_SSID = stem[2]
    WIFI_PASSWORD = stem[3]
    connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    MQTT_CLIENT_ID = ubinascii.hexlify(machine.unique_id())
    # Specific MQTT SUBSCRIBE/PUBLISH TOPICS created inside 'setup_device' function
    MQTT_SUB_TOPIC = []
    MQTT_SUB_LVL1 = b'nred2' + ESPID  # Items that are sent as part of mqtt topic will be binary (b'item)
    MQTT_REGEX = rb'nred2esp/([^/]+)/([^/]+)' # b'txt' is binary format. Required for umqttsimple to save memory
                                              # r'txt' is raw format for easier reg ex matching
                                              # 'nred2esp/+' would also work but would not return groups
                                              # () group capture. Useful for getting topic lvls in on_message
                                              # [^/] match a char except /. Needed to get topic lvl2, lvl3 groups
                                              # + will match one or more. Requiring at least 1 match forces a lvl1/lvl2/lvl3 topic structure
                                              # * could also be used for last group and then a lvl1/lvl2 topic would also be matched
    MQTT_PUB_LVL1 = b'esp2nred/'

def mqtt_connect_subscribe():
    global MQTT_CLIENT_ID, MQTT_SERVER, MQTT_SUB_TOPIC, MQTT_USER, MQTT_PASSWORD
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_SERVER, user=MQTT_USER, password=MQTT_PASSWORD)
    client.set_callback(mqtt_on_message)
    client.connect()
    main_logger.info('(CONNACK) Connected to {0} MQTT broker'.format(MQTT_SERVER))
    for topics in MQTT_SUB_TOPIC:
        client.subscribe(topics)
        main_logger.info('Subscribed to {0}'.format(topics)) 
    return client

def mqtt_on_message(topic, msg):
    global MQTT_REGEX                    # Standard variables for mqtt projects
    global mqtt_DC_speed, mqtt_DC_moving # Specific for DC motor
    main_logger.debug("Received topic(tag): {0} payload:{1}".format(topic, msg.decode("utf-8", "ignore")))
    msgmatch = re.match(MQTT_REGEX, topic)
    if msgmatch:
        mqtt_payload = ujson.loads(msg.decode("utf-8", "ignore")) # decode json data
        mqtt_topic = [msgmatch.group(0), msgmatch.group(1), msgmatch.group(2), type(mqtt_payload)]
        if mqtt_topic[1] == b'buggyZCMD':
            mqtt_DC_speed[0] = mqtt_payload['right']
            mqtt_DC_speed[1] = mqtt_payload['left']
            mqtt_DC_moving = mqtt_payload['moving']

def mqtt_reset():
    main_logger.info('Failed to connect to MQTT broker. Reconnecting...')
    utime.sleep_ms(5000)
    machine.reset()

def setup_logging(logfile, logger_type="custom", logger_name=__name__, FileMode=1, autoclose=True, logger_log_level=20, filetime=5000):
    if logger_type == 'basic': # Use basicConfig logger
        ulogging.basicConfig(level=logger_log_level) # Change logger global settings
        templogger = ulogging.getLogger(logger_name)
    elif logger_type == 'custom' and FileMode == 1:        # Using custom logger
        templogger = ulogging.getLogger(logger_name)
        templogger.setLevel(logger_log_level)
    elif logger_type == 'custom' and FileMode == 2 and not MAIN_FILE_LOGGING: # Using custom logger with output to log file
        templogger = ulogging.getLogger(logger_name, logfile, 'w', autoclose, filetime)  # w/wb to over-write, a/ab to append, autoclose (with method), file time in ms to keep file open
        templogger.setLevel(logger_log_level)
        logfiles.append(logfile)
    elif logger_type == 'custom' and FileMode == 2 and MAIN_FILE_LOGGING:            # Using custom logger with output to main log file
        templogger = ulogging.getLogger(logger_name, MAIN_FILE_NAME, MAIN_FILE_MODE, 0)  # over ride with MAIN_FILE settings in boot.py
        templogger.setLevel(logger_log_level)
    
    if MAIN_FILE_LOGGING:
        with open(MAIN_FILE_NAME, MAIN_FILE_OW) as f:
            f.write("cpu freq: {0} GHz\n".format(CPUFREQ/10**9)) 
            f.write("All module debugging will write to file: {0} with mode: {1}\n".format(MAIN_FILE_NAME, MAIN_FILE_MODE))
            if machine.reset_cause() == machine.DEEPSLEEP_RESET:
                f.write('{0}, woke from a deep sleep'.format(utime.localtime()))
        print("All module debugging will write to file: {0} with mode: {1}\n".format(MAIN_FILE_NAME, MAIN_FILE_MODE))
        logfiles.append(MAIN_FILE_NAME)   
    return templogger

def setup_device(device, lvl2, publvl3, data_keys):
    global printcolor, deviceD
    if deviceD.get(device) == None:
        deviceD[device] = {}
        deviceD[device]['data'] = {}
        deviceD[device]['lvl2'] = lvl2 # Sub/Pub lvl2 in topics. Does not have to be unique, can piggy-back on another device lvl2
        topic = MQTT_SUB_LVL1 + b"/" + deviceD[device]['lvl2'] + b"ZCMD/+"
        if topic not in MQTT_SUB_TOPIC:
            MQTT_SUB_TOPIC.append(topic)
            for key in data_keys:
                deviceD[device]['data'][key] = 0
        else:
            for key in data_keys:
                for item in deviceD:
                    if deviceD[item]['data'].get(key) != None:
                        main_logger.warning("**DUPLICATE WARNING" + device + " and " + item + " are both publishing " + key + " on " + topic)
                deviceD[device]['data'][key] = 0
        deviceD[device]['pubtopic'] = MQTT_PUB_LVL1 + lvl2 + b"/" + publvl3
        deviceD[device]['send'] = False
        printcolor = not printcolor # change color of every other print statement
        if printcolor: 
            main_logger.info("{0}{1} Subscribing to: {2}{3}".format(pcolor.LBLUE, device, topic, pcolor.ENDC))
            main_logger.info("{0}{1} Publishing  to: {2}{3}".format(pcolor.DBLUE, device, deviceD[device]['pubtopic'], pcolor.ENDC))
            main_logger.info("JSON payload keys will be:{0}{1}{2}".format(pcolor.WOLB, deviceD[device]['data'], pcolor.ENDC))
        else:
            main_logger.info("{0}{1} Subscribing to: {2}{3}".format(pcolor.PURPLE, device, topic, pcolor.ENDC))
            main_logger.info("{0}{1} Publishing  to: {2}{3}".format(pcolor.LPURPLE, device, deviceD[device]['pubtopic'], pcolor.ENDC))
            main_logger.info("JSON payload keys will be:{0}{1}{2}".format(pcolor.WOP, deviceD[device]['data'], pcolor.ENDC))
    else:
        main_logger.error("Device {0} already in use. Device name should be unique".format(device))
        sys.exit("{0}Device {1} already in use. Device name should be unique{2}".format(pcolor.RED, device, pcolor.ENDC))

# If wanting all modules to write to the same MAIN FILE then enable MAIN_FILE_LOGGING in boot.py
# If wanting modules to each write to individual files then make sure autoclose=True (safe with file open/close)
# If wanting a single module to quickly write to a log file then only enable one module and set autoclose=False
# If logger_type == 'custom'  then access to modes below
            #  FileMode == 1 # console output (no log file)
            #  FileMode == 2 # write to log file (no console output)
logfile = __name__ + '.log'
main_logger = setup_logging(logfile, 'custom', __name__, 1, True, logger_log_level=20)
main_logger.info(main_logger)

main_logger.info('localtime: {0}'.format(localdate(utime.localtime())))
if machine.reset_cause() == machine.DEEPSLEEP_RESET:
    main_logger.warning(',{0}, {1}Woke from a deep sleep{2}'.format(rtcdate(rtc.datetime()), pcolor.YELLOW, pcolor.ENDC))

# umqttsimple requires topics to be byte (b') format. For string.join to work on topics, all items must be the same, bytes.
ESPID = b'esp'  # Specific MQTT_PUB_TOPICS created at time of publishing using string.join (specifically lvl2.join)
mqtt_setup('10.0.0.115')  # Setup mqtt variables (topics and data containers) used in on_message, main loop, and publishing

deviceD = {}       # Primary container for storing all topics and data
printcolor = True
pinsummary = []
t = Timer()

#==== HARDWARE SETUP ======#
# Boot fails if pin 12 is pulled high
# Pins 34-39 are input only and do not have internal pull-up resistors. Good for ADC

DCmotorSet = {}
speedSensorON = False  # turn speed sensor on/off
frequency = 5000
mpin = [0,0]
enablePin = 0
logger_buggy = setup_logging(logfile, 'custom', 'buggy', 1, True, logger_log_level=20)
logger_encoder = setup_logging(logfile, 'custom', 'encoder', 1, True, logger_log_level=20)
mqtt_DC_speed = [0,0]
mqtt_DC_moving = 'start-up'
enc = {}

device = 'dc_motor1'
lvl2 = b'buggy'
publvl3 = ESPID + b"speedSensor"
data_keys = ['a0f', 'a1f', 'etc']
setup_device(device, lvl2, publvl3, data_keys)
DCmotorPins = [25, 26]
enablePin = 27
speedsensorPin = 17
if speedSensorON:
    enc[device] = Encoder(speedsensorPin, rpmkey='rpm1i', pulses_per_rev=20.0, min_RPM=5.0, logger=logger_encoder)
    pinsummary.append(speedsensorPin)
for i, pin in enumerate(DCmotorPins):
    mpin[i] = Pin(pin, Pin.OUT)
    pinsummary.append(pin)
enable = PWM(Pin(enablePin), frequency)
pinsummary.append(enablePin)
DCmotorSet[device] = DCMotor(mpin[0], mpin[1], enable)

device = 'dc_motor2'
lvl2 = b'buggy'
publvl3 = ESPID + b"speedSensor"
data_keys = ['a0f', 'a1f', 'etc']
setup_device(device, lvl2, publvl3, data_keys)
DCmotorPins = [32, 33]
enablePin = 23
speedsensorPin = 14
if speedSensorON:
    enc[device] = Encoder(speedsensorPin, rpmkey='rpm2i', pulses_per_rev=20.0, min_RPM=5.0, logger=logger_encoder)
    pinsummary.append(speedsensorPin)
for i, pin in enumerate(DCmotorPins):
    mpin[i] = Pin(pin, Pin.OUT)
    pinsummary.append(pin)
enable = PWM(Pin(enablePin), frequency)
pinsummary.append(enablePin)
DCmotorSet[device] = DCMotor(mpin[0], mpin[1], enable)

main_logger.info('Pins in use:{0}'.format(sorted(pinsummary)))
#==========#
# Connect and create the client
try:
    mqtt_client = mqtt_connect_subscribe()
except OSError as e:
    mqtt_reset()
# MQTT setup is successful, publish status msg and flash on-board led
mqtt_client.publish(b'esp32status', ESPID + b' connected, entering main loop')
# Period or frequency to check msgs, get data, publish msgs
on_msg_timer_ms = 400           # How frequently to check for messages. Takes ~ 2ms to check for msg
getdata_sndmsg_timer_ms =100   # How frequently to get device data and send messages. Can take > 7ms to publish msgs  
t0onmsg_ms = utime.ticks_ms()
utime.sleep_ms(250) # Number of ms delay between on_msg and data publish. Used to stagger timers for checking msgs, getting data, and publishing msgs
t0_datapub_ms = utime.ticks_ms()

t0loop_us = utime.ticks_us()
checkmsgs = False
getdata = False
sendmsgs = False
t = Timer()

while 1:

    for i, motor in enumerate(DCmotorSet.items()):
        speed = min(100, max(-100, mqtt_DC_speed[i]))
        motor.forward(speed) if speed > 0 else motor.backwards(abs(speed)) if speed < 0 else motor.stop()

    if utime.ticks_diff(utime.ticks_ms(), t0onmsg_ms) > on_msg_timer_ms:
        checkmsgs = True
        t0onmsg_ms = utime.ticks_ms()

    if utime.ticks_diff(utime.ticks_ms(), t0_datapub_ms) > getdata_sndmsg_timer_ms:
        getdata = True
        sendmsgs = True
        t0_datapub_ms = utime.ticks_ms()

    if checkmsgs:
        mqtt_client.check_msg()
        checkmsgs = False

    if getdata:
        t.start()
        if speedSensorON:         # start monitoring rpm.. can be more frequent than the reportRPM below
            for device, motor in DCmotorSet.items():
                deviceD[device]['data'] = enc[device].getdata()
                deviceD[device]['send'] = True
                if deviceD[device]['data'] is not None:
                    main_logger.debug("Got data {} {}".format(deviceD[device]['pubtopic'], ujson.dumps(deviceD[device]['data'])))       
        getdata = False
        getdata_time = t.stop()
        main_logger.debug("Get data took: {0} ms".format(getdata_time/1000))

    if sendmsgs:
        t.start()
        #buggyD = {"irpm1": 0} #{"irpm1":str(enc1.rpm), "irpm2":str(enc2.rpm), "ispeed1":str(speed1), "ispeed2":str(speed2)}
        for device, motor in DCmotorSet.items():
            if deviceD[device]['send']:
                mqtt_client.publish(deviceD[device]['pubtopic'], ujson.dumps(deviceD[device]['data']))
                main_logger.debug("Published msg {} {}".format(deviceD[device]['pubtopic'], ujson.dumps(deviceD[device]['data'])))
                deviceD[device]['send'] = False
        sendmsgs = False
        sendmsg_time = t.stop()
        main_logger.debug("Sending msg took: {0} ms".format(sendmsg_time/1000))