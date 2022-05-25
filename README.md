<a href="https://www.buymeacoffee.com/mtrab" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

# pyWorxCloud

This is a PyPI module for communicating with Worx Cloud mowers, primarily developed for use with [Home Assistant](https://home-assistant.io), but I try to keep it as wide usable as possible.<br/>
<br/>
The module are compatible with cloud enabled devices from these vendors:<br/>
- Worx Landroid
- LandXcape
- Kress

This is using and undocumented API, so do not expect everything to work.<br/>
The module will be enhanced with more functionality as the API gets mapped out - any help will be much appreciated.

### Available service calls

Service | Description | Parameters
---|---|---
update | Retrieve current status from API |
start | Start mowing routine |
pause | Pause mowing |
home | Stop (and go home) |
zonetraining | Start zonetraining |
lock | Toggle device lock |
restart | Reboot baseboard OS |
raindelay | Set new rain delay | rain_delay
toggle_schedule | Toggle schedule on or off |
toggle_partymode | Toggle party mode if supported by device |
ots | Start OTS | boundary: bool, runtime: str | int
setzone | Set next zone to mow | zone: str | int
