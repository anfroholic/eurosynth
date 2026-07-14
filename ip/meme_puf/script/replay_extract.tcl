# Standalone abstract-mode extraction replay (the round-4 fast-verify loop):
# reproduces Magic.SpiceExtraction's environment (LEF reads = abstract views,
# MAGIC_EXT_USE_GDS=0) on any post-PDN DEF, so pad<->strap<->cluster merges can
# be verified in ~2 min without running the full flow. Run inside the harden
# container:
#   DEF_PATH=/work/librelane/runs/<RUN>/22-*/chip_top.def \
#   magic -dnull -noconsole -rcfile /pdk/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc \
#         /work/ip/meme_puf/script/replay_extract.tcl
# then: grep " merge" <outdir>/chip_top.ext  (one line per net unification)
drc off
crashbackups disable
locking disable
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/techlef/gf180mcu_fd_sc_mcu7t5v0__nom.tlef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_ef_io__bi_t.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__asig_5p0.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__bi_24t.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__bi_t.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__brk2.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__brk5.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__cor.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__dvdd.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__dvss.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__fill1.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__fill10.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__fill5.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__fillnc.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__in_c.lef
lef read /pdk/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__in_s.lef
lef read /work/ip/gf180mcu_ws_ip__marker/lef/gf180mcu_ws_ip__marker.lef
lef read /work/ip/gf180mcu_ws_ip__project_id/lef/gf180mcu_ws_ip__project_id.lef
lef read /work/ip/gf180mcu_ws_ip__qrcode_id/lef/gf180mcu_ws_ip__qrcode_id.lef
lef read /work/ip/gf180mcu_ws_ip__shuttle_id/lef/gf180mcu_ws_ip__shuttle_id.lef
lef read /work/ip/meme/lef/meme.lef
lef read /work/ip/meme_puf/lef/meme_puf_cluster.lef
lef read /work/ip/meme_puf/lef/meme_puf_cluster_e.lef
lef read /work/ip/meme_puf/lef/puf_blocker.lef
lef read /work/ip/meme_puf/lef/puf_routes.lef
def read $env(DEF_PATH) -noblockage
load chip_top -dereference
cd $env(OUT_DIR)
extract do local
extract no capacitance
extract no coupling
extract no resistance
extract no adjust
extract unique notopports
extract
quit -noprompt
