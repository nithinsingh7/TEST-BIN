# DIY HOTAS for DCS World (India Build)

This is a build log and **Indian bill of materials (INR)** for a DIY fighter-jet HOTAS for **DCS World**. It's based on
[TheRaelNoisyBoi/DIY-HOTAS-Ecosystem](https://github.com/TheRaelNoisyBoi/DIY-HOTAS-Ecosystem), which provides the firmware, wiring guides and DCS export script (GPL v3).

The 3D-printable STL files and assembly instructions are sold separately on [Cults3D (NoisyBoeh)](https://cults3d.com/en/users/NoisyBoeh/3d-models) and aren't included here.

## What we are building (fighter-jet set)

| Device | Variant chosen | Why |
|---|---|---|
| HFB Joystick (base + grip) | **Hornet (F/A-18) grip** | Matches the DCS F/A-18C. Flanker grip is the alternative for Su-27/Su-33/FC. The joystick also gives you **DCS haptics** (G-load, AoA buffet, gun, touchdown). |
| Twin Engine Throttle | **Raptor (F-22)** | Has the most buttons and toggles (6 toggles, 7 push buttons), so more HOTAS functions can be bound. Felon is the alternative. |
| Rudder Pedals | — | Rudder plus separate left and right toe brakes. You need these for taxiing and carrier ops. |

I left out the Black Shark Collective because it's for helicopters only.

## Cost summary (approx., October 2026, prices incl. GST)

| BOM file | Parts cost (INR) |
|---|---:|
| [`BOM/00_Shopping_List_Fighter_Set_INR.csv`](BOM/00_Shopping_List_Fighter_Set_INR.csv): **complete set**, merged and rounded up to pack sizes | **₹ 9,762** |
| [Joystick – Hornet grip](BOM/Joystick_Hornet_F-A-18_grip_INR.csv) | ₹ 4,751 |
| [Joystick – Flanker grip](BOM/Joystick_Flanker_Su-27-30_grip_INR.csv) | ₹ 4,946 |
| [Joystick – Felon grip](BOM/Joystick_Felon_Su-57_grip_INR.csv) | ₹ 4,996 |
| [Joystick – Raptor grip](BOM/Joystick_Raptor_F-22_grip_INR.csv) | ₹ 4,806 |
| [Throttle – Raptor](BOM/Throttle_Raptor_F-22_INR.csv) | ₹ 3,933 |
| [Throttle – Felon](BOM/Throttle_Felon_Su-57_INR.csv) | ₹ 3,853 |
| [Rudder Pedals](BOM/Rudder_Pedals_INR.csv) | ₹ 2,918 |

The per-device files each count a full screw kit, spring kit and sensor pack. The merged shopping list buys those only once, so it costs less than adding the three device files together.

### Other costs not in the CSVs (estimates)

| Item | INR |
|---|---:|
| 3D-printing filament, ~3 kg PETG / PLA+ (check exact grams in the Cults3D files) | ~3,300 |
| Wiring: 28 AWG silicone wire set, Dupont/JST connectors, heat-shrink | ~750 |
| 3× USB-C **data** cables (one per device) | ~450 |
| Solder, flux, spare consumables | ~300 |
| Shipping from 3–4 online vendors | ~400 |
| **Extras subtotal** | **~5,200** |

**Estimated total for the full fighter-jet set: about ₹15,000 (₹14k–17k with spares)**, plus the cost of the Cults3D files. If you don't own a 3D printer, local printing services typically charge ₹5–10 per gram.

## Where to buy in India

- **Electronics:** [Robu.in](https://robu.in), [Robocraze](https://robocraze.com), [Probots](https://probots.co.in), [Electronicscomp](https://www.electronicscomp.com), [Hubtronics](https://hubtronics.in), Amazon.in.
- **Local markets (usually cheapest):** Lamington Road (Mumbai), SP Road (Bengaluru), Ritchie Street (Chennai), Lajpat Rai Market / Nehru Place (Delhi).
- **Bearings, bolts, threaded rod:** a local bearing or hardware shop is much cheaper than buying online.
- **AliExpress:** the upstream links are AliExpress. It's often cheaper per part, but delivery to India is slow and customs duty can apply. It's worth it for the 5-way hat switches, DS-228 buttons and PS5 thumbsticks if local stock is poor.

**Buying tips**
- Buy a **Pro Micro with USB-C, 5V/16MHz** (ATmega32U4). Don't get the 3.3V/8MHz version.
- Hall sensors, PCF8575 and ADS1115 modules are sometimes dead on arrival, so buy one spare of each.
- Generic DRV2605L modules work fine with the Adafruit library. The genuine Adafruit board costs about ₹1,100.
- The upstream rudder pedal BOM lists quantities as "TBD". The quantities in this BOM are estimates, so check them against the Cults3D assembly guide before ordering.

## Build steps

1. Print the parts and assemble them following the Cults3D instructions.
2. Wire each device using the PDF guides in the upstream [`DOCS/`](https://github.com/TheRaelNoisyBoi/DIY-HOTAS-Ecosystem/tree/main/DOCS) folder.
3. Flash the upstream [`FIRMWARE/`](https://github.com/TheRaelNoisyBoi/DIY-HOTAS-Ecosystem/tree/main/FIRMWARE) with the Arduino IDE (board: *Arduino Leonardo*). Run `I2C_Scanner.ino` first to check the wiring.
4. Give each device its own USB name and PID (see the upstream README) so DCS doesn't mix up the joystick, throttle and pedals.
5. Calibrate each device with the **Tactical MFD Control Hub** app from the upstream Releases page, or with the serial `CAL` command.
6. **DCS haptics:** copy upstream `DCS/HOTAS_Export.lua` into `Saved Games\DCS\Scripts\` and add the `dofile` line at the end of `Export.lua`.
7. In DCS, go to Options → Controls and bind the axes per aircraft (pitch/roll on the stick, throttle, rudder, toe brakes).

> All prices are estimates from Indian retailers as of October 2026. They change often, so check current prices before you order.
