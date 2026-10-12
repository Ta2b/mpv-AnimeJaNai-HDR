// Pure GPU inference timing of the AnimeJaNai SPAN models with NCNN/Vulkan: the input is uploaded
// once and stays on the GPU, the output is never downloaded. This is the ceiling a zero-copy
// Vulkan backend could reach; any frame bridge only adds to it.
// usage: bench <model stem (without .param/.bin)> <width> <height> [frames] [gpu index]
#include "net.h"
#include "gpu.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>

int main(int argc, char **argv)
{
    if (argc < 4) { std::printf("usage: bench MODEL W H [FRAMES] [GPU]\n"); return 2; }
    const std::string stem = argv[1];
    const int w = std::atoi(argv[2]), h = std::atoi(argv[3]);
    const int frames = argc > 4 ? std::atoi(argv[4]) : 100;
    ncnn::create_gpu_instance();
    const int count = ncnn::get_gpu_count();
    int index = argc > 5 ? std::atoi(argv[5]) : ncnn::get_default_gpu_index();
    for (int i = 0; i < count; i++)
        std::printf("gpu %d: %s%s\n", i, ncnn::get_gpu_info(i).device_name(), i == index ? "  <- used" : "");
    if (index < 0 || index >= count) { std::printf("no Vulkan GPU\n"); return 1; }
    ncnn::VulkanDevice *vkdev = ncnn::get_gpu_device(index);
    {
        ncnn::Net net;
        net.opt.use_vulkan_compute = true;
        net.opt.use_fp16_packed = true;
        net.opt.use_fp16_storage = true;
        net.opt.use_fp16_arithmetic = true;
        net.opt.num_threads = 2;
        net.set_vulkan_device(vkdev);
        if (net.load_param((stem + ".param").c_str()) || net.load_model((stem + ".bin").c_str())) {
            std::printf("cannot load %s\n", stem.c_str()); return 1;
        }
        ncnn::VkAllocator *blob = vkdev->acquire_blob_allocator();
        ncnn::VkAllocator *staging = vkdev->acquire_staging_allocator();
        ncnn::Option opt = net.opt;
        opt.blob_vkallocator = blob;
        opt.workspace_vkallocator = blob;
        opt.staging_vkallocator = staging;

        ncnn::Mat in(w, h, 3);
        for (int c = 0; c < 3; c++) {
            float *p = in.channel(c);
            for (int i = 0; i < w * h; i++) p[i] = (float)((i * 7 + c * 31) % 256) / 255.f;
        }
        ncnn::VkMat in_gpu;
        {
            ncnn::VkCompute cmd(vkdev);
            cmd.record_upload(in, in_gpu, opt);
            if (cmd.submit_and_wait()) { std::printf("upload failed\n"); return 1; }
        }
        auto run = [&](int n) -> double {
            int ow = 0, oh = 0;
            auto t0 = std::chrono::steady_clock::now();
            for (int i = 0; i < n; i++) {
                ncnn::VkCompute cmd(vkdev);
                ncnn::Extractor ex = net.create_extractor();
                ex.set_blob_vkallocator(blob);
                ex.set_workspace_vkallocator(blob);
                ex.set_staging_vkallocator(staging);
                ex.input("in0", in_gpu);
                ncnn::VkMat out;
                if (ex.extract("out0", out, cmd) || cmd.submit_and_wait()) { std::printf("inference failed\n"); return -1.0; }
                ow = out.w; oh = out.h;
            }
            double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count() / n;
            if (n == frames) std::printf("%dx%d -> %dx%d : %.2f ms/frame (%.1f fps)\n", w, h, ow, oh, ms, 1000.0 / ms);
            return ms;
        };
        if (run(10) < 0) return 1;      // warm-up: pipeline creation, allocator growth
        if (run(frames) < 0) return 1;
        vkdev->reclaim_blob_allocator(blob);
        vkdev->reclaim_staging_allocator(staging);
    }
    ncnn::destroy_gpu_instance();
    return 0;
}
