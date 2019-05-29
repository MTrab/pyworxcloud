import pyworxcloud
import time
from pprint import pprint

def test_func(message):
    print(message)
    print()

worx = pyworxcloud.WorxCloud("morten@trab.dk","Cm69dofz!", 0)
time.sleep(5)

attrs = vars(worx)
for item in attrs:
    print(item , ': ' , attrs[item])

#print(worx.name)
#print(worx.mac_address)
#print(worx.serial_number)
#worx.update()
#worx.return_home()