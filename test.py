import pyworxcloud

def test_func(message):
    print(message)

worx = pyworxcloud.WorxCloud("morten@trab.dk","Cm69dofz!", test_func)
print(worx.name)
print(worx.mac_address)
#worx.update()
#worx.return_home()