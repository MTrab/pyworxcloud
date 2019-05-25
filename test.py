import pyworxcloud
import time

def test_func(message):
    print(message)
    print()

worx = pyworxcloud.WorxCloud("morten@trab.dk","Cm69dofz!", 0)


while 1:
    time.sleep(0.1)
#print(worx.name)
#print(worx.mac_address)
#print(worx.serial_number)
#worx.update()
#worx.return_home()