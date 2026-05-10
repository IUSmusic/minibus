import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import minibus
from minibus import Launcher


class MinibusCoreTests(unittest.TestCase):
    def test_clean_desktop_exec_removes_field_codes(self):
        self.assertEqual(
            minibus.clean_desktop_exec('firefox %u --new-window %F'),
            'firefox  --new-window',
        )

    def test_parse_desktop_file_accepts_normal_app(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'test.desktop'
            p.write_text(
                '[Desktop Entry]\n'
                'Type=Application\n'
                'Name=My Test App\n'
                'Exec=/usr/bin/my-test %u\n',
                encoding='utf-8',
            )
            item = minibus.parse_desktop_file(p)
            self.assertIsNotNone(item)
            self.assertEqual(item.label, 'My Test App')
            self.assertEqual(item.command, '/usr/bin/my-test')
            self.assertEqual(item.kind, 'desktop')

    def test_parse_desktop_file_rejects_hidden_app(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'hidden.desktop'
            p.write_text(
                '[Desktop Entry]\n'
                'Type=Application\n'
                'Name=Hidden App\n'
                'Exec=/usr/bin/hidden\n'
                'NoDisplay=true\n',
                encoding='utf-8',
            )
            self.assertIsNone(minibus.parse_desktop_file(p))

    def test_normalise_name(self):
        self.assertEqual(minibus.normalise_name('/home/p/Apps/Super-Synth.AppImage'), 'super synth')
        self.assertEqual(minibus.normalise_name('Wine App.exe'), 'wine app')

    def test_microphone_port_heuristic(self):
        self.assertTrue(minibus.is_microphone_port('alsa_input.usb-mic:capture_FL'))
        self.assertTrue(minibus.is_microphone_port('USB Microphone:capture_FR'))
        self.assertFalse(minibus.is_microphone_port('alsa_output.pci:playback_FL'))

    def test_monitor_port_heuristic(self):
        self.assertTrue(minibus.is_monitor_port('alsa_output.pci:playback_FL'))
        self.assertTrue(minibus.is_monitor_port('Built-in Speakers:playback_FR'))
        self.assertFalse(minibus.is_monitor_port('alsa_input.usb-mic:capture_FL'))

    def test_route_allowed_blocks_mic_when_mic_off(self):
        ok, msg = minibus.route_allowed('alsa_input.usb-mic:capture_FL', 'Recorder:input_1', False, True)
        self.assertFalse(ok)
        self.assertIn('MIC is OFF', msg)

    def test_route_allowed_blocks_monitor_when_monitor_off(self):
        ok, msg = minibus.route_allowed('Firefox:output_FL', 'alsa_output.pci:playback_FL', True, False)
        self.assertFalse(ok)
        self.assertIn('MONITOR is OFF', msg)

    def test_route_allowed_accepts_non_monitor_non_mic(self):
        ok, msg = minibus.route_allowed('Firefox:output_FL', 'REAPER:input_1', False, False)
        self.assertTrue(ok)
        self.assertEqual(msg, 'OK')

    def test_detect_new_ports_preserves_order(self):
        before = ['a', 'c']
        after = ['a', 'b', 'c', 'd']
        self.assertEqual(minibus.detect_new_ports(before, after), ['b', 'd'])

    def test_best_port_for_launcher_matches_label(self):
        launcher = Launcher(label='Firefox', command='/usr/bin/firefox', kind='desktop', path='/usr/bin/firefox')
        ports = [
            'alsa_output.pci-0000_00_1f.3.analog-stereo:playback_FL',
            'Firefox:output_FL',
            'REAPER:input_1',
        ]
        self.assertEqual(minibus.best_port_for_launcher(launcher, ports), 'Firefox:output_FL')

    def test_pipewire_ports_uses_pw_link_output(self):
        def fake_run(args, timeout=4.0):
            self.assertEqual(args, ['pw-link', '-o'])
            return 0, 'Firefox:output_FL\nFirefox:output_FR\n\n', ''

        with patch.object(minibus, 'run_command', side_effect=fake_run):
            self.assertEqual(minibus.pipewire_ports('output'), ['Firefox:output_FL', 'Firefox:output_FR'])

    def test_pipewire_ports_returns_empty_on_error(self):
        with patch.object(minibus, 'run_command', return_value=(127, '', 'not found')):
            self.assertEqual(minibus.pipewire_ports('input'), [])

    def test_connect_ports_success(self):
        with patch.object(minibus, 'run_command', return_value=(0, '', '')):
            ok, msg = minibus.connect_ports('a', 'b')
            self.assertTrue(ok)
            self.assertEqual(msg, 'Connected')

    def test_connect_ports_duplicate_is_ok(self):
        with patch.object(minibus, 'run_command', return_value=(1, '', 'File exists')):
            ok, msg = minibus.connect_ports('a', 'b')
            self.assertTrue(ok)
            self.assertEqual(msg, 'Already connected')

    def test_connect_ports_rejects_missing(self):
        ok, msg = minibus.connect_ports('', 'b')
        self.assertFalse(ok)
        self.assertIn('Choose both', msg)

    def test_disconnect_ports_not_found_is_ok(self):
        with patch.object(minibus, 'run_command', return_value=(1, '', 'No such link')):
            ok, msg = minibus.disconnect_ports('a', 'b')
            self.assertTrue(ok)
            self.assertEqual(msg, 'Already disconnected')

    def test_located_binary_launcher_falls_back_to_shell_command(self):
        item = Launcher(label='tool', command='/tmp/tool', kind='binary', path='/tmp/tool')
        with patch('subprocess.Popen') as popen:
            popen.return_value = object()
            ok, msg = minibus.launch(item)
            self.assertTrue(ok)
            self.assertIn('Launched', msg)

    def test_collect_diagnostics_returns_rows(self):
        with patch.object(minibus, 'pipewire_ports', return_value=[]), \
             patch.object(minibus, 'scan_launchers', return_value=[]), \
             patch.object(minibus, 'run_command', return_value=(1, '', 'inactive')):
            rows = minibus.collect_diagnostics()
            self.assertTrue(rows)
            self.assertTrue(any(kind in {'PASS', 'WARN', 'FAIL', 'INFO'} for kind, _ in rows))

    def test_launcher_round_trip_dict(self):
        item = Launcher(label='Super Synth', command='/home/p/Super.AppImage', kind='appimage', path='/home/p/Super.AppImage')
        clone = Launcher.from_dict(item.to_dict())
        self.assertIsNotNone(clone)
        self.assertEqual(clone.label, item.label)
        self.assertEqual(clone.command, item.command)
        self.assertEqual(clone.kind, item.kind)
        self.assertEqual(clone.path, item.path)

    def test_launcher_from_dict_rejects_incomplete_data(self):
        self.assertIsNone(Launcher.from_dict({'label': 'Broken'}))
        self.assertIsNone(Launcher.from_dict(None))

    def test_short_label_truncates(self):
        self.assertEqual(minibus.short_label('ABCDEFGH', 8), 'ABCDEFGH')
        self.assertEqual(minibus.short_label('ABCDEFGHI', 8), 'ABCDEFG…')


    def test_compact_geometry_clamps_old_tall_window(self):
        self.assertEqual(minibus.compact_geometry('950x305+10+20'), '950x186+10+20')
        self.assertEqual(minibus.compact_geometry('600x900+1+2'), '780x186+1+2')

    def test_config_read_write_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            config_file = Path(td) / 'config.json'
            config_dir = Path(td)
            with patch.object(minibus, 'CONFIG_FILE', config_file), \
                 patch.object(minibus, 'CONFIG_DIR', config_dir):
                payload = {'geometry': '900x280+1+2', 'auto_refresh': False}
                minibus.write_config(payload)
                self.assertEqual(minibus.read_config(), payload)

    def test_read_config_bad_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            config_file = Path(td) / 'config.json'
            config_file.write_text('{bad json', encoding='utf-8')
            with patch.object(minibus, 'CONFIG_FILE', config_file):
                self.assertEqual(minibus.read_config(), {})


if __name__ == '__main__':
    unittest.main(verbosity=2)

class CrossPlatformBackendTests(unittest.TestCase):
    def test_audio_backend_name_windows(self):
        with patch.object(minibus.platform, 'system', return_value='Windows'):
            self.assertEqual(minibus.audio_backend_name(), 'WASAPI')
            self.assertFalse(minibus.backend_supports_patching())

    def test_audio_backend_name_macos(self):
        with patch.object(minibus.platform, 'system', return_value='Darwin'):
            self.assertEqual(minibus.audio_backend_name(), 'CoreAudio')
            self.assertFalse(minibus.backend_supports_patching())

    def test_audio_backend_name_linux(self):
        with patch.object(minibus.platform, 'system', return_value='Linux'):
            self.assertEqual(minibus.audio_backend_name(), 'PipeWire')
            self.assertTrue(minibus.backend_supports_patching())

    def test_parse_windows_endpoint_json(self):
        text = '[{"FriendlyName":"Speakers (USB Audio)"},{"FriendlyName":"Microphone Array"}]'
        self.assertEqual(
            minibus.parse_windows_endpoint_names(text),
            ['Speakers (USB Audio)', 'Microphone Array'],
        )

    def test_wasapi_ports_filters_mic_and_output(self):
        with patch.object(minibus, 'run_command', return_value=(0, '[{"FriendlyName":"Speakers"},{"FriendlyName":"USB Microphone"}]', '')), \
             patch.object(minibus.shutil, 'which', return_value='powershell'):
            self.assertIn('WASAPI::Speakers', minibus.wasapi_ports('output'))
            self.assertIn('WASAPI::USB Microphone', minibus.wasapi_ports('input'))

    def test_parse_coreaudio_devices(self):
        text = '''
Audio:
    Devices:
        MacBook Pro Speakers:
          Output Channels: 2
          Default Output Device: Yes
        MacBook Pro Microphone:
          Input Channels: 1
          Default Input Device: Yes
'''
        self.assertIn('CoreAudio::MacBook Pro Speakers', minibus.parse_coreaudio_devices(text, 'output'))
        self.assertIn('CoreAudio::MacBook Pro Microphone', minibus.parse_coreaudio_devices(text, 'input'))

    def test_non_pipewire_connect_reports_unsupported(self):
        with patch.object(minibus.platform, 'system', return_value='Windows'):
            ok, msg = minibus.connect_audio_ports('WASAPI::A', 'WASAPI::B')
            self.assertFalse(ok)
            self.assertIn('not implemented', msg)

    def test_windows_virtual_device_route_is_tracked(self):
        with patch.object(minibus.platform, 'system', return_value='Windows'):
            minibus._virtual_connections.clear()
            ok, msg = minibus.connect_audio_ports('WASAPI::Firefox', 'WASAPI::CABLE Input')
            self.assertTrue(ok)
            self.assertIn('virtual-device route', msg)
            self.assertTrue(any('CABLE Input' in link for link in minibus.current_links()))
            ok, msg = minibus.disconnect_audio_ports('WASAPI::Firefox', 'WASAPI::CABLE Input')
            self.assertTrue(ok)
            self.assertIn('virtual-device route', msg)
            minibus._virtual_connections.clear()

    def test_macos_virtual_device_route_is_tracked(self):
        with patch.object(minibus.platform, 'system', return_value='Darwin'):
            minibus._virtual_connections.clear()
            ok, msg = minibus.connect_audio_ports('CoreAudio::BlackHole 2ch', 'CoreAudio::Recorder')
            self.assertTrue(ok)
            self.assertIn('virtual-device route', msg)
            self.assertTrue(any('BlackHole 2ch' in link for link in minibus.current_links()))
            minibus._virtual_connections.clear()

    def test_non_pipewire_non_virtual_connect_still_reports_unsupported(self):
        with patch.object(minibus.platform, 'system', return_value='Windows'):
            minibus._virtual_connections.clear()
            ok, msg = minibus.connect_audio_ports('WASAPI::Speakers', 'WASAPI::Headphones')
            self.assertFalse(ok)
            self.assertIn('native app-to-app patching is not implemented', msg)

    def test_detected_virtual_devices(self):
        ports = ['WASAPI::Speakers', 'WASAPI::CABLE Input', 'WASAPI::Voicemeeter Output']
        self.assertEqual(
            minibus.detected_virtual_devices(ports),
            ['WASAPI::CABLE Input', 'WASAPI::Voicemeeter Output'],
        )

    def test_default_config_dir_uses_appdata_on_windows(self):
        with patch.object(minibus.platform, 'system', return_value='Windows'), \
             patch.dict(minibus.os.environ, {'APPDATA': r'C:\Users\Peter\AppData\Roaming'}, clear=False):
            self.assertIn('MINIBUS', str(minibus.default_config_dir()))
            self.assertIn('AppData', str(minibus.default_config_dir()))
