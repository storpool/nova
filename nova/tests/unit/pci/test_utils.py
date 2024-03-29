# Copyright (c) 2013 Intel, Inc.
# Copyright (c) 2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import glob
import os

import fixtures
import mock

from nova import exception
from nova.pci import utils
from nova import test


class PciDeviceMatchTestCase(test.NoDBTestCase):
    def setUp(self):
        super(PciDeviceMatchTestCase, self).setUp()
        self.fake_pci_1 = {'vendor_id': 'v1',
                           'device_id': 'd1',
                           'capabilities_network': ['cap1', 'cap2', 'cap3']}

    def test_single_spec_match(self):
        self.assertTrue(utils.pci_device_prop_match(
            self.fake_pci_1, [{'vendor_id': 'v1', 'device_id': 'd1'}]))
        self.assertTrue(utils.pci_device_prop_match(
            self.fake_pci_1, [{'vendor_id': 'V1', 'device_id': 'D1'}]))

    def test_multiple_spec_match(self):
        self.assertTrue(utils.pci_device_prop_match(
            self.fake_pci_1,
            [{'vendor_id': 'v1', 'device_id': 'd1'},
             {'vendor_id': 'v3', 'device_id': 'd3'}]))

    def test_spec_mismatch(self):
        self.assertFalse(utils.pci_device_prop_match(
            self.fake_pci_1,
            [{'vendor_id': 'v4', 'device_id': 'd4'},
             {'vendor_id': 'v3', 'device_id': 'd3'}]))

    def test_spec_extra_key(self):
        self.assertFalse(utils.pci_device_prop_match(
            self.fake_pci_1,
            [{'vendor_id': 'v1', 'device_id': 'd1', 'wrong_key': 'k1'}]))

    def test_spec_list(self):
        self.assertTrue(utils.pci_device_prop_match(
            self.fake_pci_1, [{'vendor_id': 'v1', 'device_id': 'd1',
                               'capabilities_network': ['cap1', 'cap2',
                                                        'cap3']}]))
        self.assertTrue(utils.pci_device_prop_match(
            self.fake_pci_1, [{'vendor_id': 'v1', 'device_id': 'd1',
                               'capabilities_network': ['cap3', 'cap1']}]))

    def test_spec_list_no_matching(self):
        self.assertFalse(utils.pci_device_prop_match(
            self.fake_pci_1, [{'vendor_id': 'v1', 'device_id': 'd1',
                               'capabilities_network': ['cap1', 'cap33']}]))

    def test_spec_list_wrong_type(self):
        self.assertFalse(utils.pci_device_prop_match(
            self.fake_pci_1, [{'vendor_id': 'v1', 'device_id': ['d1']}]))


class PciDeviceAddressParserTestCase(test.NoDBTestCase):
    def test_parse_address(self):
        self.parse_result = utils.parse_address("0000:04:12.6")
        self.assertEqual(self.parse_result, ('0000', '04', '12', '6'))

    def test_parse_address_wrong(self):
        self.assertRaises(exception.PciDeviceWrongAddressFormat,
            utils.parse_address, "0000:04.12:6")

    def test_parse_address_invalid_character(self):
        self.assertRaises(exception.PciDeviceWrongAddressFormat,
            utils.parse_address, "0000:h4.12:6")


class GetFunctionByIfnameTestCase(test.NoDBTestCase):

    @mock.patch('os.path.isdir', return_value=True)
    @mock.patch.object(os, 'readlink')
    def test_virtual_function(self, mock_readlink, *args):
        mock_readlink.return_value = '../../../0000.00.00.1'
        with mock.patch('builtins.open', side_effect=IOError()):
            address, physical_function = utils.get_function_by_ifname('eth0')
            self.assertEqual(address, '0000.00.00.1')
            self.assertFalse(physical_function)

    @mock.patch('os.path.isdir', return_value=True)
    @mock.patch.object(os, 'readlink')
    def test_physical_function(self, mock_readlink, *args):
        ifname = 'eth0'
        totalvf_path = "/sys/class/net/%s/device/%s" % (ifname,
                                                        utils._SRIOV_TOTALVFS)
        mock_readlink.return_value = '../../../0000:00:00.1'
        with self.patch_open(totalvf_path, '4') as mock_open:
            address, physical_function = utils.get_function_by_ifname('eth0')
            self.assertEqual(address, '0000:00:00.1')
            self.assertTrue(physical_function)
            mock_open.assert_called_once_with(totalvf_path)

    @mock.patch('os.path.isdir', return_value=False)
    def test_exception(self, *args):
        address, physical_function = utils.get_function_by_ifname('lo')
        self.assertIsNone(address)
        self.assertFalse(physical_function)


class IsPhysicalFunctionTestCase(test.NoDBTestCase):

    def setUp(self):
        super(IsPhysicalFunctionTestCase, self).setUp()
        self.pci_args = utils.get_pci_address_fields('0000:00:00.1')

    @mock.patch('os.path.isdir', return_value=True)
    def test_virtual_function(self, *args):
        with mock.patch('builtins.open', side_effect=IOError()):
            self.assertFalse(utils.is_physical_function(*self.pci_args))

    @mock.patch('os.path.isdir', return_value=True)
    def test_physical_function(self, *args):
        with mock.patch('builtins.open', mock.mock_open(read_data='4')):
            self.assertTrue(utils.is_physical_function(*self.pci_args))

    @mock.patch('os.path.isdir', return_value=False)
    def test_exception(self, *args):
        self.assertFalse(utils.is_physical_function(*self.pci_args))


class GetIfnameByPciAddressTestCase(test.NoDBTestCase):

    def setUp(self):
        super(GetIfnameByPciAddressTestCase, self).setUp()
        self.pci_address = '0000:00:00.1'

    @mock.patch.object(os, 'listdir')
    def test_physical_function_inferface_name(self, mock_listdir):
        mock_listdir.return_value = ['foo', 'bar']
        ifname = utils.get_ifname_by_pci_address(
            self.pci_address, pf_interface=True)
        self.assertEqual(ifname, 'bar')

    @mock.patch.object(os, 'listdir')
    def test_virtual_function_inferface_name(self, mock_listdir):
        mock_listdir.return_value = ['foo', 'bar']
        ifname = utils.get_ifname_by_pci_address(
            self.pci_address, pf_interface=False)
        self.assertEqual(ifname, 'bar')

    @mock.patch.object(os, 'listdir')
    def test_exception(self, mock_listdir):
        mock_listdir.side_effect = OSError('No such file or directory')
        self.assertRaises(
            exception.PciDeviceNotFoundById,
            utils.get_ifname_by_pci_address,
            self.pci_address
        )


class GetMacByPciAddressTestCase(test.NoDBTestCase):
    def setUp(self):
        super(GetMacByPciAddressTestCase, self).setUp()
        self.pci_address = '0000:07:00.1'
        self.if_name = 'enp7s0f1'
        self.tmpdir = self.useFixture(fixtures.TempDir())
        self.fake_file = os.path.join(self.tmpdir.path, "address")
        with open(self.fake_file, "w") as f:
            f.write("a0:36:9f:72:00:00\n")

    @mock.patch.object(os, 'listdir')
    @mock.patch.object(os.path, 'join')
    def test_get_mac(self, mock_join, mock_listdir):
        mock_listdir.return_value = [self.if_name]
        mock_join.return_value = self.fake_file
        mac = utils.get_mac_by_pci_address(self.pci_address)
        mock_join.assert_called_once_with(
            "/sys/bus/pci/devices/%s/net" % self.pci_address, self.if_name,
            "address")
        self.assertEqual("a0:36:9f:72:00:00", mac)

    @mock.patch.object(os, 'listdir')
    @mock.patch.object(os.path, 'join')
    def test_get_mac_fails(self, mock_join, mock_listdir):
        os.unlink(self.fake_file)
        mock_listdir.return_value = [self.if_name]
        mock_join.return_value = self.fake_file
        self.assertRaises(
            exception.PciDeviceNotFoundById,
            utils.get_mac_by_pci_address, self.pci_address)

    @mock.patch.object(os, 'listdir')
    @mock.patch.object(os.path, 'join')
    def test_get_mac_fails_empty(self, mock_join, mock_listdir):
        with open(self.fake_file, "w") as f:
            f.truncate(0)
        mock_listdir.return_value = [self.if_name]
        mock_join.return_value = self.fake_file
        self.assertRaises(
            exception.PciDeviceNotFoundById,
            utils.get_mac_by_pci_address, self.pci_address)

    @mock.patch.object(os, 'listdir')
    @mock.patch.object(os.path, 'join')
    def test_get_physical_function_mac(self, mock_join, mock_listdir):
        mock_listdir.return_value = [self.if_name]
        mock_join.return_value = self.fake_file
        mac = utils.get_mac_by_pci_address(self.pci_address, pf_interface=True)
        mock_join.assert_called_once_with(
            "/sys/bus/pci/devices/%s/physfn/net" % self.pci_address,
            self.if_name, "address")
        self.assertEqual("a0:36:9f:72:00:00", mac)


class GetVfNumByPciAddressTestCase(test.NoDBTestCase):

    def setUp(self):
        super(GetVfNumByPciAddressTestCase, self).setUp()
        self.pci_address = '0000:00:00.1'
        self.paths = [
            '/sys/bus/pci/devices/0000:00:00.1/physfn/virtfn3',
        ]

    @mock.patch.object(os, 'readlink')
    @mock.patch.object(glob, 'iglob')
    def test_vf_number_found(self, mock_iglob, mock_readlink):
        mock_iglob.return_value = self.paths
        mock_readlink.return_value = '../../0000:00:00.1'
        vf_num = utils.get_vf_num_by_pci_address(self.pci_address)
        self.assertEqual(vf_num, 3)

    @mock.patch.object(os, 'readlink')
    @mock.patch.object(glob, 'iglob')
    def test_vf_number_not_found(self, mock_iglob, mock_readlink):
        mock_iglob.return_value = self.paths
        mock_readlink.return_value = '../../0000:00:00.2'
        self.assertRaises(
            exception.PciDeviceNotFoundById,
            utils.get_vf_num_by_pci_address,
            self.pci_address
        )


class GetProductIDByPfPciAddressTestCase(test.NoDBTestCase):
    def setUp(self):
        super().setUp()
        self.pci_address = "0000:0a:00.0"

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/sriov_vf_device":
                    mock.mock_open(
                        read_data="101e\n"
                    )()
                }.get(f)
            )
        ),
    )
    def test_sriov_vf_device_read(self):
        product_id = utils.get_vf_product_id_by_pf_addr(self.pci_address)
        self.assertEqual(product_id, "101e")

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/sriov_vf_device":
                    mock.mock_open(
                        read_data=""
                    )()
                }.get(f)
            )
        ),
    )
    def test_sriov_vf_device_read_value_error(self):
        self.assertRaises(
            ValueError,
            utils.get_vf_product_id_by_pf_addr,
            self.pci_address,
        )

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/sriov_vf_device":
                    mock.mock_open(
                        mock=mock.MagicMock(side_effect=IOError())
                    )()
                }.get(f)
            )
        ),
    )
    def test_sriov_vf_device_read_io_error(self):
        self.assertRaises(
            ValueError,
            utils.get_vf_product_id_by_pf_addr,
            self.pci_address,
        )


class GetPciIdsByPciAddressTestCase(test.NoDBTestCase):
    def setUp(self):
        super().setUp()
        self.pci_address = "0000:0a:00.0"

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/vendor":
                    mock.mock_open(
                        read_data="0x15b3\n"
                    )(),
                    "/sys/bus/pci/devices/0000:0a:00.0/product":
                    mock.mock_open(
                        read_data="0x101e\n"
                    )(),
                }.get(f)
            )
        ),
    )
    def test_get_pci_ids(self):
        self.assertEqual(
            utils.get_pci_ids_by_pci_addr(self.pci_address), ("15b3", "101e")
        )

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/vendor": mock.mock_open(
                        read_data=""
                    )(),
                }.get(f)
            )
        ),
    )
    def test_get_pci_ids_value_error_vendor(self):
        self.assertRaises(
            ValueError,
            utils.get_pci_ids_by_pci_addr,
            self.pci_address,
        )

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/vendor":
                    mock.mock_open(
                        read_data="0x15b3\n"
                    )(),
                    "/sys/bus/pci/devices/0000:0a:00.0/product":
                    mock.mock_open(
                        read_data=""
                    )(),
                }.get(f)
            )
        ),
    )
    def test_get_pci_ids_value_error_product(self):
        self.assertRaises(
            ValueError,
            utils.get_pci_ids_by_pci_addr,
            self.pci_address,
        )

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/vendor": mock.mock_open(
                        mock=mock.MagicMock(side_effect=IOError())
                    )()
                }.get(f)
            )
        ),
    )
    def test_get_pci_ids_io_error_vendor(self):
        self.assertRaises(
            ValueError,
            utils.get_pci_ids_by_pci_addr,
            self.pci_address,
        )

    @mock.patch(
        "builtins.open",
        new=mock.MagicMock(
            side_effect=(
                lambda f: {
                    "/sys/bus/pci/devices/0000:0a:00.0/vendor":
                    mock.mock_open(
                        read_data="0x15b3\n"
                    )(),
                    "/sys/bus/pci/devices/0000:0a:00.0/product":
                    mock.mock_open(
                        mock=mock.MagicMock(side_effect=IOError())
                    )(),
                }.get(f)
            )
        ),
    )
    def test_get_pci_ids_io_error_product(self):
        self.assertRaises(
            ValueError,
            utils.get_pci_ids_by_pci_addr,
            self.pci_address,
        )
