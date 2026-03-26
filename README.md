# Dlib Installation Guide for Windows (Python 3.12)

This project requires the `dlib` library. Since compiling `dlib` from source on Windows often requires heavy dependencies like Visual Studio and CMake, using a pre-compiled `.whl` (wheel) file is the most efficient method.

## Installation Steps

1. **Download the Wheel File** Download the official pre-compiled binary for Python 3.12 from the following repository:  
   https://github.com/z-mahmud22/Dlib_Windows_Python3.x/blob/main/dlib-19.24.99-cp312-cp312-win_amd64.whl

2. **Open Terminal** Navigate to the folder where you saved the downloaded `.whl` file.

3. **Install via pip** Run the following command in your terminal:
   ```bash
   pip install dlib-19.24.99-cp312-cp312-win_amd64.whl
