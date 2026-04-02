.PHONY: init restore clean
init: sql/isuconp_data.dump benchmarker/userdata/img script/bootstrap

restore:
	DUMP_PATH=sql/isuconp_data.dump script/restore

PG_DUMP_BZ2_URL ?= https://github.com/koudaiii/ai-tour-for-partner-2026-track4-session1/releases/download/db-dump-latest/isuconp_pg17_latest.dump.bz2

sql/isuconp_data.dump.bz2:
	cd sql && \
	curl -L -o isuconp_data.dump.bz2 "$(PG_DUMP_BZ2_URL)"

sql/isuconp_data.dump: sql/isuconp_data.dump.bz2
	cd sql && \
	bunzip2 -k -f isuconp_data.dump.bz2 && \
	test -f isuconp_data.dump

script/bootstrap:
	script/bootstrap

benchmarker/userdata/img.zip:
	cd benchmarker/userdata && \
	curl -L -O https://github.com/catatsuy/private-isu/releases/download/img/img.zip

benchmarker/userdata/img: benchmarker/userdata/img.zip
	cd benchmarker/userdata && \
	unzip -qq -o img.zip

clean:
	rm -f sql/isuconp_data.dump.bz2 sql/isuconp_data.dump
	rm -f benchmarker/userdata/img.zip
	rm -rf benchmarker/userdata/img
