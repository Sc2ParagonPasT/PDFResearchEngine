import threading,unittest
from unittest.mock import patch
from repositories_v05 import Network
from adapters_v053 import BY_KEY,discover
class AdapterTests(unittest.TestCase):
    def setUp(self):self.stop=threading.Event()
    def run_adapter(self,key,responses):
        net=Network(BY_KEY[key].hosts)
        with patch.object(net,'json',side_effect=responses) as get:
            results,notes=discover(net,key,'research topic',self.stop)
        return results,notes,get
    def test_no_unapproved_network(self):
        net=Network(['archive.org'])
        with patch.object(net,'json') as get:
            for key in ('documentcloud','figshare','osf'):
                with self.assertRaisesRegex(ValueError,'Explicit domain approval'):discover(net,key,'test',self.stop)
            get.assert_not_called()
    def test_cancel_before_network(self):
        self.stop.set();net=Network(BY_KEY['internetarchive'].hosts)
        with patch.object(net,'json') as get:
            self.assertEqual(discover(net,'internetarchive','test',self.stop),([],[]));get.assert_not_called()
    def test_archive_public_pdf_and_unapproved_shard(self):
        r,n,g=self.run_adapter('internetarchive',[
            {'response':{'docs':[{'identifier':'public-book'},{'identifier':'restricted-book'}]}},
            {'metadata':{'title':'Public research','mediatype':'texts'},'d1':'ia123456.us.archive.org','files':[{'name':'public.pdf','format':'Text PDF','size':'12000','source':'original'},{'name':'private.pdf','format':'PDF','private':'true'}]},
            {'metadata':{'mediatype':'texts','access-restricted-item':'true'},'files':[{'name':'restricted.pdf','format':'PDF'}]}
        ])
        self.assertEqual(len(r),1);self.assertEqual(r[0].url,'https://archive.org/download/public-book/public.pdf')
        self.assertTrue(any('ia123456.us.archive.org' in x for x in n));self.assertEqual(g.call_count,3)
    def test_archive_file_size_and_traversal(self):
        r,n,g=self.run_adapter('internetarchive',[{'response':{'docs':[{'identifier':'book'}]}},{'metadata':{'mediatype':'texts'},'files':[{'name':'../escape.pdf','format':'PDF'},{'name':'big.pdf','format':'PDF','size':'999999999'},{'name':'private.pdf','format':'PDF','private':True}]}])
        self.assertEqual(r,[])
    def test_documentcloud_only_public_approved_asset(self):
        r,n,g=self.run_adapter('documentcloud',[{'results':[
            {'title':'Public report','access':'public','asset_url':'https://assets.documentcloud.org/documents/1/','slug':'public-report'},
            {'title':'Private','access':'private','pdf_url':'https://assets.documentcloud.org/private.pdf'},
            {'title':'Outside','access':'public','pdf_url':'https://outside.example/x.pdf'},
        ]}])
        self.assertEqual(len(r),1);self.assertTrue(r[0].url.endswith('/public-report.pdf'))
        self.assertTrue(any('outside.example' in x for x in n))
    def test_figshare_metadata_and_public_files(self):
        r,n,g=self.run_adapter('figshare',[
            {'data':[{'attributes':{'doi':'10.6084/m9.figshare.123.v2','state':'findable'}},{'attributes':{'doi':'10.1234/other'}}]},
            {'title':'Research topic','doi':'10.6084/m9.figshare.123.v2','is_public':True,'files':[
                {'name':'article.pdf','downloadUrl':'https://ndownloader.figshare.com/files/123','size':12345},
                {'name':'external.pdf','is_link_only':True,'downloadUrl':'https://outside.example/x.pdf'},
                {'name':'data.csv','downloadUrl':'https://ndownloader.figshare.com/files/234'}]}
        ])
        self.assertEqual(len(r),1);self.assertEqual(r[0].identifier,'10.6084/m9.figshare.123.v2')
        self.assertTrue(g.call_args_list[1].args[0].endswith('/articles/123/versions/2'))
    def test_osf_public_file_relationship(self):
        r,n,g=self.run_adapter('osf',[
            {'data':[{'attributes':{'title':'Research topic','is_published':True},'relationships':{'primary_file':{'links':{'related':{'href':'https://api.osf.io/v2/files/a/'}}}}},
                {'attributes':{'title':'Withdrawn','date_withdrawn':'2024-01-01'},'relationships':{}},
                {'attributes':{'title':'Outside'},'relationships':{'primary_file':{'links':{'related':{'href':'https://outside.example/file'}}}}}]},
            {'data':{'attributes':{'name':'article.pdf','size':1234},'links':{'download':'https://files.osf.io/v1/resources/a/providers/osfstorage/b'}}}
        ])
        self.assertEqual(len(r),1);self.assertEqual(g.call_count,2)
    def test_no_implicit_pdf_from_unknown_metadata(self):
        r,n,g=self.run_adapter('documentcloud',[{'results':[{'title':'Report','access':'public','source_url':'https://assets.documentcloud.org/x.pdf'}]}])
        self.assertEqual(r,[]);self.assertTrue(n)
