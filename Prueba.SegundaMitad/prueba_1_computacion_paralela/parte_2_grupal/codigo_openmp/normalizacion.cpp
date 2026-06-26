#include <omp.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

struct Options {
    std::size_t rows = 50'000'000;
    int cols = 16;
    double nan_rate = 0.035;
    std::uint64_t seed = 4128090;
    bool csv = false;
};

static std::uint64_t splitmix64(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

static double unit01(std::uint64_t x) {
    return (splitmix64(x) >> 11) * (1.0 / 9007199254740992.0);
}

static double synthetic_value(std::size_t row, int col, std::uint64_t seed) {
    const double u = unit01(seed + row * 1315423911ULL + static_cast<std::uint64_t>(col) * 2654435761ULL);
    const double v = unit01(seed ^ (row * 11400714819323198485ULL + static_cast<std::uint64_t>(col + 17) * 104729ULL));

    switch (col) {
        case 0: return -55.0 + 125.0 * u;                         // latitude-like
        case 1: return -180.0 + 360.0 * u;                         // longitude-like
        case 2: return 120.0 + 780.0 * std::sqrt(u);               // velocity-like
        case 3: return 60.0 + 39'000.0 * u;                        // barometric altitude
        case 4: return -4'000.0 + 8'000.0 * (u - 0.5);             // vertical rate
        case 5: return 360.0 * u;                                  // heading
        case 6: return 1.0 + 80.0 * u + 8.0 * std::sin(v * 6.283); // signal-like score
        case 7: return std::log1p(1500.0 * u) * 120.0;
        default: return (static_cast<double>(col) + 1.0) * (u - 0.5) + std::sin(v * 12.0);
    }
}

static Options parse_args(int argc, char** argv) {
    Options opt;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        auto require_value = [&](const std::string& name) -> char* {
            if (i + 1 >= argc) {
                std::cerr << "Falta valor para " << name << "\n";
                std::exit(2);
            }
            return argv[++i];
        };

        if (arg == "--rows") {
            opt.rows = static_cast<std::size_t>(std::strtoull(require_value(arg), nullptr, 10));
        } else if (arg == "--cols") {
            opt.cols = std::atoi(require_value(arg));
        } else if (arg == "--nan-rate") {
            opt.nan_rate = std::atof(require_value(arg));
        } else if (arg == "--seed") {
            opt.seed = static_cast<std::uint64_t>(std::strtoull(require_value(arg), nullptr, 10));
        } else if (arg == "--csv") {
            opt.csv = true;
        } else if (arg == "--help") {
            std::cout << "Uso: normalizacion [--rows N] [--cols C] [--nan-rate R] [--seed S] [--csv]\n";
            std::exit(0);
        } else {
            std::cerr << "Argumento no reconocido: " << arg << "\n";
            std::exit(2);
        }
    }
    if (opt.rows == 0 || opt.cols <= 0 || opt.nan_rate < 0.0 || opt.nan_rate >= 1.0) {
        std::cerr << "Parametros invalidos.\n";
        std::exit(2);
    }
    return opt;
}

static void fill_matrix(std::vector<double>& x, const Options& opt) {
    const std::size_t total = opt.rows * static_cast<std::size_t>(opt.cols);

    #pragma omp parallel for schedule(static)
    for (std::int64_t idx = 0; idx < static_cast<std::int64_t>(total); ++idx) {
        const std::size_t pos = static_cast<std::size_t>(idx);
        const std::size_t row = pos / static_cast<std::size_t>(opt.cols);
        const int col = static_cast<int>(pos % static_cast<std::size_t>(opt.cols));
        const double miss = unit01(opt.seed ^ (pos * 0x9e3779b97f4a7c15ULL));

        if (miss < opt.nan_rate) {
            x[pos] = std::numeric_limits<double>::quiet_NaN();
        } else {
            x[pos] = synthetic_value(row, col, opt.seed);
        }
    }
}

static void column_stats(const std::vector<double>& x,
                         std::size_t rows,
                         int cols,
                         std::vector<double>& sums,
                         std::vector<double>& sums_sq,
                         std::vector<std::uint64_t>& counts) {
    const int max_threads = omp_get_max_threads();
    std::vector<double> thread_sums(static_cast<std::size_t>(max_threads * cols), 0.0);
    std::vector<double> thread_sums_sq(static_cast<std::size_t>(max_threads * cols), 0.0);
    std::vector<std::uint64_t> thread_counts(static_cast<std::size_t>(max_threads * cols), 0);

    #pragma omp parallel
    {
        const int tid = omp_get_thread_num();
        double* local_sum = thread_sums.data() + static_cast<std::size_t>(tid * cols);
        double* local_sum_sq = thread_sums_sq.data() + static_cast<std::size_t>(tid * cols);
        std::uint64_t* local_count = thread_counts.data() + static_cast<std::size_t>(tid * cols);

        #pragma omp for schedule(static)
        for (std::int64_t r = 0; r < static_cast<std::int64_t>(rows); ++r) {
            const std::size_t base = static_cast<std::size_t>(r) * static_cast<std::size_t>(cols);
            for (int c = 0; c < cols; ++c) {
                const double value = x[base + static_cast<std::size_t>(c)];
                if (!std::isnan(value)) {
                    local_sum[c] += value;
                    local_sum_sq[c] += value * value;
                    local_count[c] += 1;
                }
            }
        }
    }

    std::fill(sums.begin(), sums.end(), 0.0);
    std::fill(sums_sq.begin(), sums_sq.end(), 0.0);
    std::fill(counts.begin(), counts.end(), 0);

    for (int t = 0; t < max_threads; ++t) {
        const std::size_t offset = static_cast<std::size_t>(t * cols);
        for (int c = 0; c < cols; ++c) {
            sums[c] += thread_sums[offset + static_cast<std::size_t>(c)];
            sums_sq[c] += thread_sums_sq[offset + static_cast<std::size_t>(c)];
            counts[c] += thread_counts[offset + static_cast<std::size_t>(c)];
        }
    }
}

int main(int argc, char** argv) {
    const Options opt = parse_args(argc, argv);
    const std::size_t total = opt.rows * static_cast<std::size_t>(opt.cols);

    std::vector<double> x;
    try {
        x.resize(total);
    } catch (const std::bad_alloc&) {
        std::cerr << "No se pudo reservar memoria para " << total << " valores double.\n";
        return 1;
    }

    const double t_generate0 = omp_get_wtime();
    fill_matrix(x, opt);
    const double t_generate1 = omp_get_wtime();

    std::vector<double> sums(static_cast<std::size_t>(opt.cols));
    std::vector<double> sums_sq(static_cast<std::size_t>(opt.cols));
    std::vector<std::uint64_t> counts(static_cast<std::size_t>(opt.cols));
    std::vector<double> means(static_cast<std::size_t>(opt.cols), 0.0);
    std::vector<double> stdevs(static_cast<std::size_t>(opt.cols), 1.0);

    const double t_fit0 = omp_get_wtime();
    column_stats(x, opt.rows, opt.cols, sums, sums_sq, counts);

    for (int c = 0; c < opt.cols; ++c) {
        if (counts[c] > 0) {
            means[c] = sums[c] / static_cast<double>(counts[c]);
            const double variance = std::max(sums_sq[c] / static_cast<double>(counts[c]) - means[c] * means[c], 0.0);
            stdevs[c] = std::sqrt(variance);
            if (stdevs[c] == 0.0) {
                stdevs[c] = 1.0;
            }
        }
    }
    const double t_fit1 = omp_get_wtime();

    const double t_transform0 = omp_get_wtime();
    #pragma omp parallel for schedule(static)
    for (std::int64_t idx = 0; idx < static_cast<std::int64_t>(total); ++idx) {
        const std::size_t pos = static_cast<std::size_t>(idx);
        const int col = static_cast<int>(pos % static_cast<std::size_t>(opt.cols));
        double value = x[pos];
        if (!std::isnan(value)) {
            x[pos] = (value - means[col]) / stdevs[col];
        }
    }
    const double t_transform1 = omp_get_wtime();

    std::vector<double> check_sums(static_cast<std::size_t>(opt.cols));
    std::vector<double> check_sums_sq(static_cast<std::size_t>(opt.cols));
    std::vector<std::uint64_t> check_counts(static_cast<std::size_t>(opt.cols));
    const double t_validate0 = omp_get_wtime();
    column_stats(x, opt.rows, opt.cols, check_sums, check_sums_sq, check_counts);
    const double t_validate1 = omp_get_wtime();

    double max_abs_mean = 0.0;
    double max_std_error = 0.0;
    std::uint64_t valid_values = 0;
    for (int c = 0; c < opt.cols; ++c) {
        valid_values += check_counts[c];
        if (check_counts[c] == 0) {
            continue;
        }
        const double mean = check_sums[c] / static_cast<double>(check_counts[c]);
        const double variance = std::max(check_sums_sq[c] / static_cast<double>(check_counts[c]) - mean * mean, 0.0);
        max_abs_mean = std::max(max_abs_mean, std::abs(mean));
        max_std_error = std::max(max_std_error, std::abs(std::sqrt(variance) - 1.0));
    }

    const double generate_s = t_generate1 - t_generate0;
    const double fit_s = t_fit1 - t_fit0;
    const double transform_s = t_transform1 - t_transform0;
    const double validate_s = t_validate1 - t_validate0;
    const double total_s = fit_s + transform_s;

    std::cout << std::fixed << std::setprecision(6);
    if (opt.csv) {
        std::cout << "threads,rows,cols,nan_rate,valid_values,generate_s,fit_s,transform_s,validate_s,total_s,max_abs_mean,max_std_error\n";
        std::cout << omp_get_max_threads() << ','
                  << opt.rows << ','
                  << opt.cols << ','
                  << opt.nan_rate << ','
                  << valid_values << ','
                  << generate_s << ','
                  << fit_s << ','
                  << transform_s << ','
                  << validate_s << ','
                  << total_s << ','
                  << max_abs_mean << ','
                  << max_std_error << '\n';
    } else {
        std::cout << "Normalizacion masiva con OpenMP\n";
        std::cout << "Filas: " << opt.rows << " | Columnas: " << opt.cols << " | NaN: " << opt.nan_rate << "\n";
        std::cout << "Hilos OpenMP: " << omp_get_max_threads() << "\n";
        std::cout << "Valores validos: " << valid_values << " de " << total << "\n";
        std::cout << "Generacion: " << generate_s << " s\n";
        std::cout << "Calculo de estadisticos: " << fit_s << " s\n";
        std::cout << "Transformacion: " << transform_s << " s\n";
        std::cout << "Validacion: " << validate_s << " s\n";
        std::cout << "Tiempo normalizacion: " << total_s << " s\n";
        std::cout << "Max |media| posterior: " << max_abs_mean << "\n";
        std::cout << "Max error std posterior: " << max_std_error << "\n";
    }

    return 0;
}
