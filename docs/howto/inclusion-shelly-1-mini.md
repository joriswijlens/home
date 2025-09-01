# Please mind:
- Enable zigbee switches off access point
- Enabling access point disables zigbee

## Inclusion of Shelly-1 Mini in zigbee2mqtt
- Factory reset - hold button for 10 seconds on shelly-1 mini
- Press and hold for 5 seconds to enable Device access point and Bluetooth connection.
- Connect to the Shelly-1 Mini access point by selecting the WiFi network "shelly1pm-xxxxxx" 
- Open a web browser and navigate to 192.168.33.1
- MQTT settings
  - Enable MQTT
  - Set the MQTT server to your mosquitto broker address <ha host name>.local:1883
  - Menu zigbee
  - Enable Zigbee
  - Restart the device
 - zigbee2mqtt
   - Go to the zigbee2mqtt web interface
   - Go to Settings > Devices
   - Click on "Permit join" to allow new devices to join the network
   - Already paired devices will be listed here
   - If not Press 3 consecutive times to put the Device in Zigbee inclusion mode

 - Problem after initiating state change switch physical switch is out of sync so physical switch needs to clicked twice to change state.

 - Press and hold the button for 5 seconds to enable Device access point and Bluetooth connection.
 - Go to the Shelly-1 Mini access point
 - Set the input type to "Edge"
 - ENABLE ZIGBEE AGAIN, because enabling access point disables zigbee
  - Menu zigbee
  - Enable Zigbee
 - Restart the device
 - Got to zigbee2mqtt
 - Problem solved after setting input type to edge

# Resources
- https://kb.shelly.cloud/knowledge-base/shelly-1pm-mini-gen4#Shelly1PMMiniGen4-Deviceidentification
- https://www.reddit.com/r/ShellyUSA/comments/1eaayq8/shelly_1_mini_g3_how_come_the_toggle_and_edge/