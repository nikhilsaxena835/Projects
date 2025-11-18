/*
energy_map = > CV_32F
cumulativeMap = > CV_32F
https://stackoverflow.com/a/7014918/19558433
Create a console application
Add opencv_world4100.lib
Point compiler to opencv/build/include
Point linker to vc16/libs
*/

#include <iostream>
#include <opencv2/opencv.hpp>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <filesystem>   



using namespace cv;
using namespace std;
using namespace filesystem;

class SeamCarving {

private:
    char* filename;
    int outputWidth;
    int outputHeight;
    Mat inputImage, outputImage;

public:
    SeamCarving(char* filenameInput, int outwidth, int outheight) {
        filename = filenameInput;
        outputWidth = outwidth;
        outputHeight = outheight;

        inputImage = imread(filename);
        outputImage = resizeImage(inputImage, outputHeight, outputWidth);
        saveResult(filename);
    }


    Mat removeVerticalSeam(const Mat& image, const Mat& seam) {
        int height = image.rows;
        int width = image.cols;

        Mat resizedImage(height, width - 1, CV_8UC3);

        for (int i = 0; i < height; i++) {
            int seamCol = seam.at<int>(i, 0);

            for (int j = 0; j < width - 1; ++j) {
                if (j < seamCol) {
                    resizedImage.at<Vec3b>(i, j) = image.at<Vec3b>(i, j);
                }
                else {
                    resizedImage.at<Vec3b>(i, j) = image.at<Vec3b>(i, j + 1);
                }
            }
        }

        return resizedImage;
    }

    Mat removeHorizontalSeam(Mat& image, Mat& seam) {
        int rows = image.rows;
        int cols = image.cols;

        Mat new_image(rows - 1, cols, image.type());

        for (int j = 0; j < cols; ++j) {
            int seam_row = seam.at<int>(0, j);

            for (int i = 0; i < seam_row; ++i) {
                new_image.at<Vec3b>(i, j) = image.at<Vec3b>(i, j);
            }

            for (int i = seam_row; i < rows - 1; ++i) {
                new_image.at<Vec3b>(i, j) = image.at<Vec3b>(i + 1, j);
            }
        }
        return new_image;
    }

    Mat identifyVerticalSeam(const Mat& energyMap) {
        int height = energyMap.rows;
        int width = energyMap.cols;

        Mat costMatrix(height, width, CV_32S);
        energyMap.convertTo(costMatrix, CV_32S);

        for (int i = 1; i < height; ++i) {
            for (int j = 0; j < width; ++j) {
                int minEnergy = costMatrix.at<int>(i - 1, j);

                if (j > 0) {
                    minEnergy = min(minEnergy, costMatrix.at<int>(i - 1, j - 1));
                }

                if (j < width - 1) {
                    minEnergy = min(minEnergy, costMatrix.at<int>(i - 1, j + 1));
                }

                
                

                costMatrix.at<int>(i, j) += minEnergy;
            }
        }

        Mat seam(height, 1, CV_32S, Scalar(-1));
        int minCol = 0;
        int minVal = numeric_limits<int>::max();

        for (int j = 0; j < width; ++j) {
            if (costMatrix.at<int>(height - 1, j) < minVal) {
                minVal = costMatrix.at<int>(height - 1, j);
                minCol = j;
            }
        }

        for (int i = height - 1; i >= 0; --i) {
            seam.at<int>(i, 0) = minCol;
            if (i > 0) {
                int prev = minCol;
                minCol = prev;

                if (prev < width - 1 && costMatrix.at<int>(i - 1, prev + 1) < costMatrix.at<int>(i - 1, minCol)) {
                    minCol = prev + 1;
                }

                if (prev > 0 && costMatrix.at<int>(i - 1, prev - 1) < costMatrix.at<int>(i - 1, minCol)) {
                    minCol = prev - 1;
                }
                
            }
        }
        return seam;
    }

    Mat identifyHorizontalSeam(const Mat& energyMap) {
        int rows = energyMap.rows;
        int cols = energyMap.cols;

        if (rows == 0 || cols == 0) {
            throw std::invalid_argument("Energy map.");
        }

        Mat costMatrix(rows, cols, CV_32S, Scalar::all(0));
        Mat backtrack(rows, cols, CV_32S, Scalar::all(-1));
        Mat seam(1, cols, CV_32S);

        energyMap.col(0).convertTo(costMatrix.col(0), CV_32S);

        for (int j = 1; j < cols; ++j) {
            for (int i = 0; i < rows; ++i) {
                int currentCost = energyMap.at<uchar>(i, j);
                int minCost = costMatrix.at<int>(i, j - 1);
                int minIndex = i;

                if (i < rows - 1 && costMatrix.at<int>(i + 1, j - 1) < minCost) {
                    minCost = costMatrix.at<int>(i + 1, j - 1);
                    minIndex = i + 1;
                }

                if (i > 0 && costMatrix.at<int>(i - 1, j - 1) < minCost) {
                    minCost = costMatrix.at<int>(i - 1, j - 1);
                    minIndex = i - 1;
                }

                backtrack.at<int>(i, j) = minIndex;

                costMatrix.at<int>(i, j) = currentCost + minCost;
            }
        }

        int minCost = costMatrix.at<int>(0, cols - 1);
        int minIndex = 0;

        for (int i = 1; i < rows; ++i) {
            if (costMatrix.at<int>(i, cols - 1) < minCost) {
                minCost = costMatrix.at<int>(i, cols - 1);
                minIndex = i;
            }
        }
        for (int j = cols - 1; j >= 0; --j) {
            seam.at<int>(0, j) = minIndex;
            minIndex = backtrack.at<int>(minIndex, j);
        }

        return seam;
    }
   

    Mat computeScharrEnergy(const Mat& channel) {

        Mat grad_x, grad_y, abs_grad_x_f, abs_grad_y_f, energy;

        Scharr(channel, grad_x, CV_32F, 1, 0);  // Scharr operator for x-direction
        Scharr(channel, grad_y, CV_32F, 0, 1);  // Scharr operator for y-direction

        // grad_x_f and grad_y_f have final scaled, absolute and 8 bitted values.
        convertScaleAbs(grad_x, abs_grad_x_f);
        convertScaleAbs(grad_y, abs_grad_y_f);

        add(abs_grad_x_f, abs_grad_y_f, energy);

        return energy;
    }


    Mat calculateEnergyMap(const Mat& outputImage)
    {
        Mat b, g, r;
        Mat channels[3];
        split(outputImage, channels);
        b = channels[0];
        g = channels[1];
        r = channels[2];

        //Using Scharr operator as it gives better performance than Soble
        //https://docs.opencv.org/4.x/d5/d0f/tutorial_py_gradients.html


        Mat b_energy = computeScharrEnergy(b);
        Mat g_energy = computeScharrEnergy(g);
        Mat r_energy = computeScharrEnergy(r);

        Mat total_energy;
        add(b_energy, g_energy, total_energy);
        add(total_energy, r_energy, total_energy);
        normalize(total_energy, total_energy, 0, 255, NORM_MINMAX);

        total_energy.convertTo(total_energy, CV_8UC3);
       
        return total_energy;
    }

    Mat resizeImage(const Mat& image, int newHeight, int newWidth) {
        Mat resizedImage = image.clone();
        int currentHeight = image.rows;
        int currentWidth = image.cols;

        Mat energyMap = calculateEnergyMap(resizedImage);


        while (currentWidth > newWidth) {
            Mat seam = identifyVerticalSeam(energyMap);
            resizedImage = removeVerticalSeam(resizedImage, seam);
            currentWidth--;
        }

        while (currentHeight > newHeight) {
            Mat seam = identifyHorizontalSeam(energyMap);
            resizedImage = removeHorizontalSeam(resizedImage, seam);
            currentHeight--;
        }
        return resizedImage;
    }

    void saveResult(const string& filename) {
        
        path p = current_path();
        string stringpath = p.generic_string();

        //string outputPath = stringpath+"/out"+filename;
        string outputPath = "out_" + filename;
        if (imwrite(outputPath, outputImage)) {
            //namedWindow("image", WINDOW_AUTOSIZE);
            cout << "Image saved successfully to " << outputPath << endl;
           // imshow("Demo", outputImage);
           // waitKey(30000);
        }
        else {
            cerr << "Error: Could not save the image to " << filename << endl;
        }
    }

};


int main(int argc, char**argv)
{
   // /*
    //cout << argc << endl;
        if (argc != 4)
        cout << "Entered Invalid Arguments";
    else {
        int h = stoi(argv[2]);
        int w = stoi(argv[3]);
        SeamCarving* obj = new SeamCarving(argv[1], h, w);
    }
   // */
    //SeamCarving* obj = new SeamCarving((char*)"sample4.jpeg", 700, 500);

}