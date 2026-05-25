# Solix BLE F1500 Fork

Home Assistant custom integration fork for `solix_ble`, focused on improving support for the Anker SOLIX F1500.

## What This Fork Adds

- F1500 model detection and dedicated device class
- F1500 telemetry request handling for split `c840` response packets
- Additional F1500 sensors:
  - battery, temperature, firmware, serial number
  - AC/DC/USB/solar power readings
  - remaining time
  - charging-status estimate
  - max/min battery percentage candidates
- Additional F1500 controls:
  - AC output switch
  - DC output switch
  - display on/off switch
  - light mode select
  - display brightness select
  - display timeout select

## Repository Layout

The integration lives in:

`custom_components/solix_ble`

This fork currently keeps the original Home Assistant domain name, `solix_ble`.

## Important Notes

- This fork is tuned specifically for F1500 experimentation.
- Some F1500 mappings are still best-effort and need real-device validation.
- A few readouts are intentionally marked by implementation style as inferred rather than fully confirmed.

## Next Good Steps

1. Validate each sensor against the physical device.
2. Confirm display/light state telemetry keys.
3. Confirm battery limit telemetry keys.
4. Clean up debug logging once mappings are stable.
5. Publish to GitHub and add release notes.

## Local Development

This repo was created from a working Home Assistant `/config/custom_components/solix_ble` tree.

To install manually, copy:

`custom_components/solix_ble`

into your Home Assistant `config/custom_components/` directory.
