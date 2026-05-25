"""F1500 support for Solix BLE."""

from __future__ import annotations
import logging
import time
from datetime import datetime, timedelta

from SolixBLE.const import (
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.devices.generic import Generic
from SolixBLE.states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus

CMD_AC_OUTPUT = "404a"
CMD_DC_OUTPUT = "404b"
CMD_LIGHT_MODE = "404f"
CMD_DISPLAY_MODE = "404c"
CMD_DISPLAY_TIMEOUT = "4046"
CMD_DISPLAY_ON_OFF = "4052"

PAYLOAD_ON = "a10121a2020101"
PAYLOAD_OFF = "a10121a2020100"
PAYLOAD_LIGHT_MODE = "a10121a20201"
PAYLOAD_TIMEOUT_TIME = "a10121a20302"

_LOGGER = logging.getLogger(__name__)


class F1500(Generic):
    """Anker SOLIX F1500 / A1772."""

    _EXPECTED_TELEMETRY_LENGTH: int = 240
    _EXPECTED_SMALL_FRAGMENT_MIN: int = 40
    _EXPECTED_SMALL_FRAGMENT_MAX: int = 80
    _EXPECTED_LARGE_FRAGMENT_MIN: int = 230
    _TELEMETRY_PATTERN: str = "03010f"
    _PUSH_TELEMETRY_COMMANDS: set[str] = {"4402"}
    _REQUEST_TELEMETRY_COMMAND: str = "c840"

    def _has_key(self, key: str) -> bool:
        return self._data is not None and key in self._data

    async def connect(self, max_attempts: int = 3, run_callbacks: bool = True) -> bool:
        _LOGGER.debug(
            "F1500 connect start: address=%s max_attempts=%s run_callbacks=%s",
            getattr(self, "address", "unknown"),
            max_attempts,
            run_callbacks,
        )
        connected = await super().connect(
            max_attempts=max_attempts, run_callbacks=run_callbacks
        )
        _LOGGER.debug(
            "F1500 connect result: connected=%s available=%s client=%s",
            connected,
            getattr(self, "available", None),
            self._client is not None,
        )
        if not connected:
            return False

        try:
            _LOGGER.debug("F1500 requesting initial status update after connect")
            await self.get_status_update()
        except Exception:
            _LOGGER.exception("Failed to request initial F1500 status update")

        return True

    async def get_status_update(self) -> dict[str, bytes]:
        """Request a telemetry update from the device.

        F1500 often negotiates successfully but does not immediately push a
        telemetry frame, so we explicitly request one after connect/reconnect.
        """
        _LOGGER.debug(
            "F1500 sending status update request: cmd=4040 payload=a10121"
        )
        await self._send_command(
            cmd=bytes.fromhex("4040"),
            payload=bytes.fromhex("a10121"),
        )

        _LOGGER.debug(
            "F1500 waiting for requested telemetry packets: pattern=%s cmd=%s",
            self._TELEMETRY_PATTERN,
            self._REQUEST_TELEMETRY_COMMAND,
        )
        packet_1 = await self._listen_for_packet(
            bytes.fromhex(self._TELEMETRY_PATTERN),
            bytes.fromhex(self._REQUEST_TELEMETRY_COMMAND),
        )
        if not packet_1:
            _LOGGER.debug("F1500 requested telemetry packet 1 wait returned no packet")
            raise TimeoutError("Timed out waiting for F1500 telemetry packet 1")

        _LOGGER.debug(
            "F1500 received requested telemetry packet 1: length=%s hex=%s",
            len(packet_1),
            packet_1.hex(),
        )

        packet_2 = await self._listen_for_packet(
            bytes.fromhex(self._TELEMETRY_PATTERN),
            bytes.fromhex(self._REQUEST_TELEMETRY_COMMAND),
        )
        if not packet_2:
            _LOGGER.debug("F1500 requested telemetry packet 2 wait returned no packet")
            raise TimeoutError("Timed out waiting for F1500 telemetry packet 2")

        _LOGGER.debug(
            "F1500 received requested telemetry packet 2: length=%s hex=%s",
            len(packet_2),
            packet_2.hex(),
        )

        new_payload = packet_1[1:] + packet_2[1:]
        _LOGGER.debug(
            "F1500 merging requested telemetry packets: packet_1=%s packet_2=%s merged=%s",
            len(packet_1),
            len(packet_2),
            len(new_payload),
        )
        decrypted_payload = self._decrypt_payload(new_payload)
        _LOGGER.debug(
            "F1500 requested telemetry decrypted payload: %s",
            decrypted_payload.hex(),
        )
        parameters = self._parse_payload(decrypted_payload)

        _LOGGER.debug(
            "F1500 requested status parameters (%s keys): %s",
            len(parameters),
            self._parameters_to_str(parameters, types=True),
        )
        self._data = parameters
        self._last_data_timestamp = datetime.now()
        self._run_state_changed_callbacks()
        return parameters

    def _parse_version(self, key: str) -> str:
        if self._data is None:
            return DEFAULT_METADATA_STRING
        return ".".join([digit for digit in str(self._parse_int(key, begin=1))])

    @property
    def hours_remaining(self) -> float:
        if self._data is None:
            return DEFAULT_METADATA_FLOAT
        return round(divmod(self.time_remaining, 24)[1], 1)

    @property
    def days_remaining(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return round(divmod(self.time_remaining, 24)[0])

    @property
    def time_remaining(self) -> float:
        if self._data is None:
            return DEFAULT_METADATA_FLOAT
        return self._parse_int("a4", begin=1) / 10.0

    @property
    def timestamp_remaining(self) -> datetime | None:
        if self._data is None:
            return None
        return datetime.now() + timedelta(hours=self.time_remaining)

    @property
    def battery_percentage(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("c1", begin=1)

    @property
    def battery_percentage_expansion(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("c2", begin=1)

    @property
    def battery_health(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("c3", begin=1)

    @property
    def battery_health_expansion(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("c4", begin=1)

    @property
    def num_expansion(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("c5", begin=1)

    @property
    def charging_status(self) -> str:
        if self._data is None:
            return DEFAULT_METADATA_STRING

        # F1500 has not yet been mapped to a confirmed charging-status key.
        # Fall back to a power-flow inference so the state is still visible.
        power_in = self.power_in
        power_out = self.power_out
        if power_in == DEFAULT_METADATA_INT or power_out == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_STRING
        if power_in == 0 and power_out == 0:
            return ChargingStatus.IDLE.name.lower()
        if power_in > power_out:
            return ChargingStatus.CHARGING.name.lower()
        if power_out > power_in:
            return ChargingStatus.DISCHARGING.name.lower()
        return ChargingStatus.IDLE.name.lower()

    @property
    def max_battery_percentage(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        if self._has_key("d9"):
            return self._parse_int("d9", begin=4, end=5)
        if self._has_key("c0"):
            return self._parse_int("c0", begin=1)
        return DEFAULT_METADATA_INT

    @property
    def min_battery_percentage(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        if self._has_key("d9"):
            return self._parse_int("d9", begin=5, end=6)
        return DEFAULT_METADATA_INT

    @property
    def power_out(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("a5", begin=1)

    @property
    def power_in(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self.ac_power_in + self.solar_power_in

    @property
    def ac_power_in(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("af", begin=1)

    @property
    def ac_power_out(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("b0", begin=1)

    @property
    def solar_power_in(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("ae", begin=1)

    @property
    def dc_power_out(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("ad", begin=1)

    @property
    def usb_c1_power(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("a7", begin=1)

    @property
    def usb_c2_power(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("a8", begin=1)

    @property
    def usb_a1_power(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("a9", begin=1)

    @property
    def usb_a2_power(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("aa", begin=1)

    @property
    def usb_a3_power(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("ab", begin=1)

    @property
    def usb_a4_power(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("ac", begin=1)

    @property
    def software_version(self) -> str:
        return self._parse_version("b3")

    @property
    def software_version_controller(self) -> str:
        return self._parse_version("ba")

    @property
    def ac_output(self) -> PortStatus:
        if self._data is None:
            return PortStatus.UNKNOWN
        return PortStatus(self._parse_int("bb", begin=1))

    @property
    def dc_output(self) -> PortStatus:
        if self._data is None:
            return PortStatus.UNKNOWN
        return PortStatus(self._parse_int("bc", begin=1))

    @property
    def software_version_expansion(self) -> str:
        return self._parse_version("b9")

    @property
    def serial_number(self) -> str:
        if self._data is None:
            return DEFAULT_METADATA_STRING
        return self._parse_string("d0", begin=1)

    @property
    def temperature(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("bd", begin=1, signed=True)

    @property
    def temperature_expansion(self) -> int:
        if self._data is None:
            return DEFAULT_METADATA_INT
        return self._parse_int("be", begin=1, signed=True)

    @property
    def light(self) -> LightStatus:
        if self._data is None:
            return LightStatus.UNKNOWN
        return LightStatus(self._parse_int("cf", begin=1))

    async def turn_ac_on(self) -> None:
        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_OUTPUT), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_ac_off(self) -> None:
        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_OUTPUT), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def turn_dc_on(self) -> None:
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_dc_off(self) -> None:
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def turn_display_on(self) -> None:
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_ON_OFF), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_display_off(self) -> None:
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_ON_OFF), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def set_light_mode(self, mode: LightStatus) -> None:
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the light status to unknown")
        await self._send_command(
            cmd=bytes.fromhex(CMD_LIGHT_MODE),
            payload=bytes.fromhex(PAYLOAD_LIGHT_MODE) + mode.value.to_bytes(),
        )

    async def set_display_mode(self, mode: LightStatus) -> None:
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the display brightness to unknown")
        if mode is LightStatus.SOS:
            raise ValueError("You cannot set the display brightness to SOS")
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_MODE),
            payload=bytes.fromhex(PAYLOAD_LIGHT_MODE) + mode.value.to_bytes(),
        )

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:
        if timeout is DisplayTimeout.UNKNOWN:
            raise ValueError("You cannot set the display timeout to unknown")
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_TIMEOUT),
            payload=bytes.fromhex(PAYLOAD_TIMEOUT_TIME)
            + timeout.value.to_bytes(length=2, byteorder="little", signed=False),
        )

    async def _process_notification(self, client, handle: int, data: bytes) -> None:
        if self._client is not client:
            _LOGGER.debug("Ignoring notification from old client")
            return

        self._last_packet_timestamp = time.time()
        pattern, cmd, payload = self._split_packet(data)
        _LOGGER.debug(
            "F1500 notification received: handle=%s total_len=%s pattern=%s cmd=%s payload_len=%s",
            handle,
            len(data),
            pattern.hex(),
            cmd.hex(),
            len(payload),
        )

        pattern_hex = pattern.hex()
        cmd_hex = cmd.hex()

        if pattern_hex == self._TELEMETRY_PATTERN and cmd_hex in self._PUSH_TELEMETRY_COMMANDS:
            _LOGGER.debug(
                "Received F1500 telemetry message on handle %s with cmd %s and payload length %s",
                handle,
                cmd_hex,
                len(payload),
            )

            if len(payload) == self._EXPECTED_TELEMETRY_LENGTH:
                await self._process_encrypted_telemetry_payload(cmd, payload)
                return

            if self._EXPECTED_SMALL_FRAGMENT_MIN <= len(payload) <= self._EXPECTED_SMALL_FRAGMENT_MAX:
                _LOGGER.debug(
                    "Storing small F1500 telemetry fragment (%s bytes)",
                    len(payload),
                )
                self._telemetry_payload_small = payload
            elif len(payload) >= self._EXPECTED_LARGE_FRAGMENT_MIN:
                _LOGGER.debug(
                    "Storing large F1500 telemetry fragment (%s bytes)",
                    len(payload),
                )
                self._telemetry_payload_large = payload
            else:
                _LOGGER.warning(
                    "Telemetry payload has an unexpected length of %s", len(payload)
                )

            if (
                self._telemetry_payload_small is None
                or self._telemetry_payload_large is None
            ):
                _LOGGER.debug(
                    "Waiting for matching F1500 telemetry fragment. small=%s large=%s",
                    None if self._telemetry_payload_small is None else len(self._telemetry_payload_small),
                    None if self._telemetry_payload_large is None else len(self._telemetry_payload_large),
                )
                return

            new_payload = self._telemetry_payload_large + self._telemetry_payload_small
            _LOGGER.debug(
                "Combining F1500 telemetry fragments: large=%s small=%s total=%s",
                len(self._telemetry_payload_large),
                len(self._telemetry_payload_small),
                len(new_payload),
            )
            self._telemetry_payload_large = None
            self._telemetry_payload_small = None

            await self._process_encrypted_telemetry_payload(cmd, new_payload)
            return

        await super()._process_notification(client, handle, data)

    async def _process_encrypted_telemetry_payload(
        self, cmd: bytes, payload: bytes
    ) -> None:
        _LOGGER.debug(
            "F1500 processing encrypted telemetry payload: cmd=%s payload_len=%s payload=%s",
            cmd.hex(),
            len(payload),
            payload.hex(),
        )
        if len(payload) != self._EXPECTED_TELEMETRY_LENGTH:
            _LOGGER.debug(
                "F1500 telemetry payload length is %s, expected %s",
                len(payload),
                self._EXPECTED_TELEMETRY_LENGTH,
            )

        decrypted_payload = self._decrypt_payload(payload)
        _LOGGER.debug("F1500 decrypted telemetry payload: %s", decrypted_payload.hex())
        parameters = self._parse_payload(decrypted_payload)
        _LOGGER.debug(
            "F1500 telemetry parameters (%s keys): %s",
            len(parameters),
            self._parameters_to_str(parameters, types=True),
        )
        await self._process_telemetry(cmd, parameters)
