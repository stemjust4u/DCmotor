import ulogging
from machine import Pin

class RotaryEncoder:
    def __init__(self, clkPin, dtPin, button, key1='RotEncCi', key2='RotEncBi', logger=None):
        self.clkPin = Pin(clkPin, Pin.IN, Pin.PULL_UP)
        self.dtPin = Pin(dtPin, Pin.IN, Pin.PULL_UP)
        self.button = Pin(button, Pin.IN, Pin.PULL_UP)
        self.outgoing = {}
        self.og_counter = key1
        self.og_button = key2
        if logger is not None:                         # Use logger passed as argument
            self.logger = logger
        else:                                          # Root logger already exists and no custom logger passed
            self.logger = ulogging.getLogger(__name__) # Create from root logger
        self.clkLastState = self.clkPin.value()
        self.clkState = self.clkPin.value()
        self.dtState = self.dtPin.value()
        self.button.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=self._button_callback) # link interrupt handler to function for pin falling or rising
        self.logger.info('Rotary Encoder pins- clk:{0} data:{1} button:{2}'.format(self.clkPin, self.dtPin, self.button))
        self.counter = 0
        self.clkUpdate = True
        self.buttonpressed = False
        
    def _is_integer(self, n):
        if n == None or n == "na":
            return False
        if isinstance(n, int):
            return True
        if abs(round(n) - n) == 0.5:
            return False
        else:
            return True
    
    def _button_callback(self, pin):
        self.buttonpressed = True
  
    def getdata(self):
        self.clkState = self.clkPin.value()
        self.dtState = self.dtPin.value()
        if self.clkState != self.clkLastState or self.buttonpressed:
            if self.clkState != self.clkLastState:
                if self.dtState != self.clkState:
                    self.counter -= 0.5
                else:
                    self.counter += 0.5
                self.clkLastState = self.clkState
            self.logger.debug('counter:{0} dtState:{1} clkState:{2} button:{3}'.format(self.counter, self.dtState, self.clkState, self.buttonpressed))
            buttonstate = self.button.value()
            self.buttonpressed = False
            if self._is_integer(self.counter):
                self.outgoing[self.og_counter] = self.counter
                self.outgoing[self.og_button] = buttonstate
                self.logger.debug(self.outgoing)
                return self.outgoing

if __name__ == "__main__":
    logger_rotenc = ulogging.getLogger('rotenc')
    logger_rotenc.setLevel(10)
    clkPin, dtPin, button_rotenc = 15, 4, 2
    data_keys = ['RotEncCi', 'RotEncBi']
    rotEnc1 = RotaryEncoder(clkPin, dtPin, button_rotenc, data_keys[0], data_keys[1], logger_rotenc)
    while True:
        clicks = rotEnc1.getdata()
        if clicks is not None:
            print(clicks)