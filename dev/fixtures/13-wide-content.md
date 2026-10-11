## Build commands, old and new

A note that starts with a subheading, and holds things wider than a phone: a long command in
backticks, `pants run projects/data/scripts/prepare_input.py -- --input=/tmp/sample_200k.jsonl`,
a bare URL, https://storage.example.com/buckets/exported_filtered_pairs/part-00000-of-00128.parquet,
and a path, `gs://example-processed/exported_filtered_pairs/part-*.parquet`.

| Target                                   | Old (pants)                    | New (bazel)                           | Rows      |
| ---------------------------------------- | ------------------------------ | ------------------------------------- | --------- |
| `natural_reasoning_sample_deduplicated`  | `pants fix path/to/file.py`    | `bazel run //:fix -- path/to/file.py` | 774,356   |
| `stackexchange_filtered_pairs`           | `pants test path/to/test.py`   | `bazel test //path/to:target_test`    | 5,000     |

After the table, a code block, which may scroll sideways on its own:

```bash
python launchers/batch.py entrypoints run_batch --config=configs/stem_20260611_phase1.yaml --num_shards=1
```
