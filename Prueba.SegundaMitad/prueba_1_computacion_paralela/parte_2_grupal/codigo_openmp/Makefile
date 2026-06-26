CXX ?= g++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -pedantic -fopenmp
TARGET = normalizacion
SRC = normalizacion.cpp

.PHONY: all clean run

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(SRC) -o $(TARGET)

run: $(TARGET)
	OMP_NUM_THREADS=4 ./$(TARGET) --rows 5000000

clean:
	rm -f $(TARGET) $(TARGET).exe
