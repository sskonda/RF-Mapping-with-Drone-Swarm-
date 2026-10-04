# The runner loads one testbench before executing this macro.
# Record interface signals and accessible internals for waveform review.
onerror {quit -f -code 1}
log -r /*
run -all
quit -f
