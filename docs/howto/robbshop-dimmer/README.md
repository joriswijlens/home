## Samenvatting dimmer-probleem

- Nieuwe **Robbshop 2-draads Zigbee dimmer** geïnstalleerd.
- Probleem: lamp bleef **nagloeien** bij uitschakelen.
- Eerst geprobeerd met een **bypass** in de plafonddoos, maar dit hielp niet direct.
- Verwarring over de aansluitingen:
    - Bij 2-draads sluit je **fase** zowel op `L` als op `N` aan.
    - `⊗` is de uitgang naar de lamp (geschakelde fase).
    - De **echte nul (blauw)** gaat rechtstreeks naar de lamp, nooit via de dimmer.
- Oude conventionele dimmers hadden dit probleem niet, omdat die de fase volledig onderbraken.
- Oplossing: een **officiële Robbshop bypass** plaatsen → voorkomt nagloeien en maakt de dimmer stabiel.

✅ Conclusie: met de juiste aansluiting en een Robbshop-bypass is het nagloeiprobleem verdwenen.  
Voor de rest werkt de dimmer perfect in Home Assistant makkelijk te paren via Zigbee2MQTT.

Als je een neutrale draad hebt, geen bypass nodig.