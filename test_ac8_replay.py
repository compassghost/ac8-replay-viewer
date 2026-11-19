import unittest,struct
from ac8_replay import lz4_block,FormatError,Reader,tagged_value
class CodecTests(unittest.TestCase):
 def test_lz4_literal(self):self.assertEqual(lz4_block(b'\x50hello',5),b'hello')
 def test_lz4_overlapping_match(self):self.assertEqual(lz4_block(b'\x15a\x01\x00',10),b'a'*10)
 def test_corrupt_lz4(self):
  for data,n in [(b'\x00\x00\x00',4),(b'\x50hi',5),(b'\x50hello',4),(b'\x50hello',6)]:
   with self.assertRaises(FormatError):lz4_block(data,n)
 def test_unicode_fstring(self):self.assertEqual(Reader(struct.pack('<i',-3)+'空中\0'.encode('utf-16le')).string(),'空中')
 def test_fstring_length_rejected(self):
  with self.assertRaises(FormatError):Reader(struct.pack('<i',2)+b'no').string()
 def test_native_struct_and_bool_flags(self):
  self.assertEqual(tagged_value({'data':struct.pack('<q',1234),'type':{'name':'StructProperty','params':[{'name':'DateTime'}]},'flags':8}),1234)
  self.assertTrue(tagged_value({'data':b'','type':{'name':'BoolProperty'},'flags':16}))
if __name__=='__main__':unittest.main()
