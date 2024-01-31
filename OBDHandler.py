import obd
import time
import math
import json

# obd.logger.setLevel(obd.logging.DEBUG)

MAX_SPEED = 150

class OBDHandler():
    def __init__(self):

        ports = obd.scan_serial()      # return list of valid USB or RF ports
        print(ports)
        
        # Choose OBDII port
        while True:
            try:
                self.obd_port = int(input("Please choose your port [0-"+str(len(ports)-1)+"]"))
                if 0 <= self.obd_port <= int(len(ports)):
                    break
                else:
                    print("Port number is not valid. Please try again")
            except ValueError:
                print("Input not recognized. Try again")


        # Create connection
        self.connection = obd.OBD(ports[self.obd_port], baudrate=9600, protocol="7", fast=False) # auto-connects to USB or RF port

        # Set max RPM
        while True:
            try:
                self.max_rpm = int(input("Please enter your car's redline RPM [e.g. 4500, 8000]: "))
                if 0 <= self.max_rpm <= 15000:
                    break
                else:
                    print("Max RPM must be between 0 - 15000")
            except ValueError:
                print("Input not recognized. Try again")

        # Reset values
        self.speed = 0
        self.rpm = 0
        self.pedal = 0
        self.min_pedal = 0.0
        self.max_pedal = 1.0

    def get_speed(self):
        cmd = obd.commands.SPEED
        response = self.connection.query(cmd)
        return response.value.to("kph").magnitude

    def get_rpm(self):
        cmd = obd.commands.RPM
        response = self.connection.query(cmd)
        return response.value.magnitude
    
    def get_pedal(self):
        cmd = obd.commands.ACCELERATOR_POS_D
        # cmd = obd.commands[1][17] # Uncomment for emulator use only
        response = self.connection.query(cmd)
        response_percent = response.value.magnitude
        # response_percent = (response.value.magnitude-19.9)*0.02 # Slightly modified lesageethan's percentage formula for Carmony
        if response_percent<0:
            return 0
        return response_percent# user-friendly unit conversions
    
    def get_raw_pedal(self):
        cmd = obd.commands.ACCELERATOR_POS_D
        response=self.connection.query(cmd)
        response_percent = response.value.magnitude
        return response_percent
    
    def get_redline(self):
        # Read file
        with open("car_ranges.json", "r") as json_file:
            car_values = json.load(json_file)
            return car_values["redline"]
    
    def get_idle(self):
        # Read file
        with open("car_ranges.json", "r") as json_file:
            car_values = json.load(json_file)
            return car_values["idle"]
        
    def get_pedal_minmax(self):
        # Read file
        with open("car_ranges.json", "r") as json_file:
            car_values = json.load(json_file)
            return car_values["pedal"]

    def refresh_values(self): # Also taken from lesageethan's Carmony
        self.speed = self.get_speed()
        self.rpm = self.get_rpm()
        self.pedal = self.get_pedal()
    
    def pedal_to_freq(self, percentage):
        r= 20000 * percentage + 3 # Formula calculated using https://www.dcode.fr/function-equation-finder
        if r < 200 : r = 200 
        elif r > 20000 : r = 20000
        return r
    
    def rpm_to_freq(self, percentage):
        r= 68241*percentage-13525.3 # Formula calculated using https://www.dcode.fr/function-equation-finder
        if r < 200 : r = 200 
        elif r > 20000 : r = 20000
        return r
    
    def speed_to_freq(self, percentage):
        r=1874.42*math.log(2079.27*percentage+0.0331104)+6587.76 # Formula calculated using https://www.dcode.fr/function-equation-finder
        if r < 200 : r = 200 
        elif r > 20000 : r = 20000
        return r
    
    def speed_to_vol(self, percentage):
        r = 5.49451*percentage**2+3.9011*percentage
        if r > 1 : r=1
        return r

    def rpm_to_vol(self, percentage):
        r = 25.1634*percentage**0.0395332-23.8083
        if r < 0 : r = 0 
        elif r > 1 : r = 1
        return r
    
    def pedal_to_vol(self, percentage):
        return percentage

    
    def normalize_value(self, curr, min_value, max_value):
        curr = max(min_value, curr)
        max_value = max(min_value, max_value)

        normalized_value = curr / max_value

        normalized_value = min(1, max(min_value, normalized_value))

        return normalized_value
    
    def calibrate_pedal(self):
        print("Pedal calibration will now begin. Please put your key in MAR position (Engine off) and press ENTER when you're ready")

        min_values = []
        max_values = []

        # Get min pedal value
        print("LIFT your foot COMPLETELY from the GAS PEDAL and wait 3 seconds...")
        time.sleep(3)
        for i in range(1,5):
            print("["+str(i)+"] Reading pedal information...")
            min_values.append(self.get_raw_pedal())
            time.sleep(0.5)
        
        self.min_pedal = sum(min_values) / len(min_values)
        print("MIN Pedal value: "+str(self.min_pedal))

        time.sleep(1)

        input("Maximum pedal value measurement will now begin.\nPlease get ready to push your gas pedal and press ENTER to continue...")

        # Get max pedal value
        print("PUSH your GAS PEDAL to FULL and hold it still...")
        time.sleep(2)
        for i in range(1,5):
            print("!KEEP PUSHING!")
            print("["+str(i)+"] Reading pedal information...")
            max_values.append(self.get_raw_pedal())
            time.sleep(0.5)

        self.max_pedal = sum(max_values) / len(max_values)
        print("MAX Pedal value: "+str(self.max_pedal))

        print("✅ Calibration complete ✅")

        return [self.min_pedal, self.max_pedal]
             


    def get_percentages(self):
        self.refresh_values()
        return {
            "speed": self.normalize_value(self.speed, 0 , MAX_SPEED), # Speed_normalized = 2/300 * real speed
            "rpm": self.normalize_value(self.rpm, self.get_idle() , self.get_redline()),
            "pedal": self.normalize_value(self.pedal, self.get_pedal_minmax()[0], self.get_pedal_minmax()[1])
        }
    
    def get_frequencies(self):
        self.refresh_values() # Auto refresh values
        return {
            "speed": self.speed_to_freq(self.normalize_value(self.speed, 0 , MAX_SPEED)),
            "rpm": self.rpm_to_freq(self.normalize_value(self.rpm, self.get_idle() , self.get_redline())),
            "pedal": self.pedal_to_freq(self.normalize_value(self.pedal, self.get_pedal_minmax()[0], self.get_pedal_minmax()[1]))
        }
    
    def get_volumes(self):
        self.refresh_values() # Auto refresh values
        return {
            "speed": self.speed_to_vol(self.normalize_value(self.speed, 0 , MAX_SPEED)),
            "rpm": self.rpm_to_vol(self.normalize_value(self.rpm, self.get_idle() , self.get_redline())),
            "pedal": self.pedal_to_vol(self.normalize_value(self.pedal, self.get_pedal_minmax()[0], self.get_pedal_minmax()[1]))
        }