# F1500 Notes

## Confirmed Working Areas

- BLE connect and encryption negotiation
- Requested telemetry flow using split `c840` packets
- Core sensors for battery, temperature, firmware, serial number, and power values

## Areas Still Under Validation

- AC/DC status key mapping
- Light state key mapping
- Display brightness state key mapping
- Display timeout state key mapping
- Max/min battery percentage telemetry mapping
- Charging status telemetry mapping

## Publishing Notes

- If this fork should replace upstream in HACS, keeping domain `solix_ble` is fine.
- If this fork should coexist alongside upstream, the domain must be renamed.
