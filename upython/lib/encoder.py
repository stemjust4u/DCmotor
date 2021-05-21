from machine import Pin
import time, ulogging, utime
import micropython

micropython.alloc_emergency_exception_buf(100)

class Encoder:
    def __init__(self, dtPin, rpmkey='rpmi', pulses_per_rev=20, min_RPM=5, logger=None):
        self.rpmkey = rpmkey
        self.outgoing = {}
        self.dtPin = Pin(dtPin, Pin.IN, Pin.PULL_UP)
        self.pulses_per_rev = pulses_per_rev
        if logger is not None:                         # Use logger passed as argument
            self.logger = logger
        else:                                          # Root logger already exists and no custom logger passed
            self.logger = ulogging.getLogger(__name__) # Create from root logger
        self.dtPin.irq(trigger=Pin.IRQ_RISING, handler=self._callback)
        self.logger.info('Encoder pins- data:{0}'.format(self.dtPin))
        self._t0 = utime.ticks_us()
        self.numPeriods = 3
        self._period = [0]*self.numPeriods
        self.c = 0
        self.min_RPM = min_RPM

    def _callback(self, pin):
        self._period[self.c] = utime.ticks_diff(utime.ticks_us(), self._t0)
        self._t0 = utime.ticks_us()
        self.c += 1
        if self.c == self.numPeriods: self.c = 0
        #if self._period is not None: self.logger.debug(self._period)
        
    def getdata(self):
        RPM = 0
        self.logger.debug(self._period)
        if self._period is not None and sum(self._period) > 0:
            RPM = int(60000000 / ((sum(self._period)/len(self._period)) * self.pulses_per_rev))
        if RPM < self.min_RPM:
            RPM = 0
        self.outgoing[self.rpmkey] = RPM
        return self.outgoing

if __name__ == '__main__':

    logger_enc = ulogging.getLogger('enc')
    logger_enc.setLevel(10)
    dtPin = 26
    RUN_TIME = 60000 # ms
    SAMPLE_TIME = 1.0
    encoder1 = Encoder(dtPin, rpmkey='rpmi', pulses_per_rev=20.0, min_RPM=5.0, logger=logger_enc)
    start = utime.ticks_ms()
    while utime.ticks_diff(utime.ticks_ms(), start) < RUN_TIME:
        rpm = encoder1.getdata()
        print(rpm)
        utime.sleep_ms(500)