### Basic example using this module

import asyncio
import pyworxcloud

async def main():
    worx = pyworxcloud.WorxCloud()

    # Initialize connection, using your worx email and password
    auth = worx.initialize("your@email","Password")

    if not auth:
        #If invalid credentials are used, or something happend during
        #authorize, then exit
        exit(0)

    
    #Connect to device with index 0 (devices are enumerated 0, 1, 2 ...) and do
    #not verify SSL (False)
    worx.connect(0, False)

    #Force and update request to get latest state from the device
    worx.update()
    
    #Read latest states received from the device
    worx.getStatus()

    #Print all attributes received from the device
    attrs = vars(worx)
    for item in attrs:
        print(item , ':' , attrs[item])

    
    ### Below are examples on calling actions - uncomment the one you want to test.

    #Set rain delay to 60 minutes
    #worx.setRainDelay(60)

    #Start mowing routine
    #worx.start()

    #Pause mowing
    #worx.pause()

    #Stop and return to base
    #worx.stop()


asyncio.get_event_loop().run_until_complete(main())