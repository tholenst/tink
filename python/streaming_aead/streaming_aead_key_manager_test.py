# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for tink.python.streaming_aead_key_manager."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import io

from absl.testing import absltest
from tink.proto import aes_ctr_hmac_streaming_pb2
from tink.proto import aes_gcm_hkdf_streaming_pb2
from tink.proto import common_pb2
from tink.proto import tink_pb2
from tink.python import tink_config
from tink.python.core import tink_error
from tink.python.streaming_aead import streaming_aead
from tink.python.streaming_aead import streaming_aead_key_manager
from tink.python.streaming_aead import streaming_aead_key_templates


class TestBytesObject(io.BytesIO):
  """A BytesIO object that does not close."""

  def close(self):
    pass


def setUpModule():
  tink_config.register()


class StreamingAeadKeyManagerTest(absltest.TestCase):

  def setUp(self):
    super(StreamingAeadKeyManagerTest, self).setUp()
    self.key_manager_gcm = streaming_aead_key_manager.from_cc_registry(
        'type.googleapis.com/google.crypto.tink.AesGcmHkdfStreamingKey')
    self.key_manager_ctr = streaming_aead_key_manager.from_cc_registry(
        'type.googleapis.com/google.crypto.tink.AesCtrHmacStreamingKey')

  def test_primitive_class(self):
    self.assertEqual(self.key_manager_gcm.primitive_class(),
                     streaming_aead.StreamingAead)
    self.assertEqual(self.key_manager_ctr.primitive_class(),
                     streaming_aead.StreamingAead)

  def test_key_type(self):
    self.assertEqual(
        self.key_manager_gcm.key_type(),
        'type.googleapis.com/google.crypto.tink.AesGcmHkdfStreamingKey')
    self.assertEqual(
        self.key_manager_ctr.key_type(),
        'type.googleapis.com/google.crypto.tink.AesCtrHmacStreamingKey')

  def test_new_key_data(self):
    # AES GCM HKDF
    key_template = streaming_aead_key_templates.AES128_GCM_HKDF_4KB
    key_data = self.key_manager_gcm.new_key_data(key_template)
    self.assertEqual(key_data.type_url, self.key_manager_gcm.key_type())
    self.assertEqual(key_data.key_material_type, tink_pb2.KeyData.SYMMETRIC)
    key = aes_gcm_hkdf_streaming_pb2.AesGcmHkdfStreamingKey()
    key.ParseFromString(key_data.value)
    self.assertEqual(key.version, 0)
    self.assertLen(key.key_value, 16)
    self.assertEqual(key.params.hkdf_hash_type, common_pb2.HashType.SHA256)
    self.assertEqual(key.params.derived_key_size, 16)
    self.assertEqual(key.params.ciphertext_segment_size, 4096)

    # AES CTR HMAC
    key_template = streaming_aead_key_templates.AES128_CTR_HMAC_SHA256_4KB
    key_data = self.key_manager_ctr.new_key_data(key_template)
    self.assertEqual(key_data.type_url, self.key_manager_ctr.key_type())
    self.assertEqual(key_data.key_material_type, tink_pb2.KeyData.SYMMETRIC)
    key = aes_ctr_hmac_streaming_pb2.AesCtrHmacStreamingKey()
    key.ParseFromString(key_data.value)
    self.assertEqual(key.version, 0)
    self.assertLen(key.key_value, 16)
    self.assertEqual(key.params.hkdf_hash_type, common_pb2.HashType.SHA256)
    self.assertEqual(key.params.derived_key_size, 16)
    self.assertEqual(key.params.hmac_params.hash, common_pb2.HashType.SHA256)
    self.assertEqual(key.params.hmac_params.tag_size, 32)
    self.assertEqual(key.params.ciphertext_segment_size, 4096)

  def test_invalid_params_throw_exception(self):
    # AES GCM HKDF
    key_template = streaming_aead_key_templates.create_aes_gcm_hkdf_streaming_key_template(
        63, common_pb2.HashType.SHA1, 65, 55)
    with self.assertRaisesRegex(tink_error.TinkError,
                                'key_size must not be smaller than'):
      self.key_manager_gcm.new_key_data(key_template)

    # AES CTR HKDF
    key_template = streaming_aead_key_templates.create_aes_ctr_hmac_streaming_key_template(
        63, common_pb2.HashType.SHA1, 65, common_pb2.HashType.SHA256, 55, 2)
    with self.assertRaisesRegex(tink_error.TinkError,
                                'key_size must not be smaller than'):
      self.key_manager_ctr.new_key_data(key_template)

  def test_encrypt_decrypt(self):
    saead_primitive = self.key_manager_ctr.primitive(
        self.key_manager_ctr.new_key_data(
            streaming_aead_key_templates.AES128_CTR_HMAC_SHA256_4KB))
    plaintext = b'plaintext'
    aad = b'associated_data'

    # Encrypt
    ct_destination = TestBytesObject()
    with saead_primitive.new_encrypting_stream(ct_destination, aad) as es:
      self.assertLen(plaintext, es.write(plaintext))
    self.assertNotEqual(ct_destination.getvalue(), plaintext)

    # Decrypt
    ct_source = TestBytesObject(ct_destination.getvalue())
    with saead_primitive.new_decrypting_stream(ct_source, aad) as ds:
      self.assertEqual(ds.read(), plaintext)

  def test_encrypt_decrypt_wrong_aad(self):
    saead_primitive = self.key_manager_ctr.primitive(
        self.key_manager_ctr.new_key_data(
            streaming_aead_key_templates.AES128_CTR_HMAC_SHA256_4KB))
    plaintext = b'plaintext'
    aad = b'associated_data'

    # Encrypt
    ct_destination = TestBytesObject()
    with saead_primitive.new_encrypting_stream(ct_destination, aad) as es:
      self.assertLen(plaintext, es.write(plaintext))
    self.assertNotEqual(ct_destination.getvalue(), plaintext)

    # Decrypt
    ct_source = TestBytesObject(ct_destination.getvalue())
    with saead_primitive.new_decrypting_stream(ct_source, b'bad ' + aad) as ds:
      with self.assertRaises(tink_error.TinkError):
        ds.read()


if __name__ == '__main__':
  absltest.main()
