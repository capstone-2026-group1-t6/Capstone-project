import json

meta = [json.loads(l) for l in open('data/index/corpus_meta.jsonl').readlines() if l.strip()]
cited = [
    'dsid_a141594a1ec0490c91300bfb085e9e79_0001',
    'dsid_f214759205094806bc7750bb36de7e29_0001',
    'dsid_56507a4977e04e0fabd01bdf8988b3d2_0001',
    'dsid_95fc21f6c370441e86b67c802333d787_0001',
    'dsid_a141594a1ec0490c91300bfb085e9e79_0003',
    'dsid_df6511e6fa0b44e4a07ba87e0fa9e3a5_0003',
    'dsid_9ed01291d81947f49500df5fb28ab724_0013',
    'dsid_1b3840b2c6804e22bd5017390fdc36c2_0001',
    'dsid_0b7c50ad45a340b9a4800058635ab96a_0002',
    'dsid_a0afc86b80144cbb87755a8d82c07edb_0005',
]
for m in meta:
    if m.get('chunk_id') in cited:
        print(f'--- {m["chunk_id"]} (source: {m["source"]}) ---')
        print(m['text'][:400])
        print()
