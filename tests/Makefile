export PYTHONWARNINGS = error,ignore::DeprecationWarning:distutils,ignore::DeprecationWarning:site,ignore::FutureWarning

regression_tests :=  $(shell ls test_AHB/)

.PHONY: $(regression_tests)

SIM?=verilator

all: $(regression_tests)

$(regression_tests):
	cd test_AHB/$@ && $(MAKE) SIM=$(SIM)



clean:
	$(foreach TEST, $(regression_tests), $(MAKE) -C test_AHB/$(TEST) clean;)

regression:
	$(foreach TEST, $(regression_tests), $(MAKE) -C test_AHB/$(TEST) regression;)
