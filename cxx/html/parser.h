#ifndef TGSERVER_HTML_PARSER_H
#define TGSERVER_HTML_PARSER_H

#include <string>
#include <unordered_map>

namespace html {
    static const std::string META_PREFIX = "<meta property=";

    class parser {
    private:
        using siter = std::string::iterator;

    private:
        static bool starts_with(siter it, siter end, std::string const &prefix) {
            size_t p = 0;
            while (p < prefix.size() && it < end && *it == prefix[p]) {
                p++;
                it++;
            }
            return p == prefix.size();
        }

        static siter skip_until(siter start, siter end, char c) {
            while (start != end && *start != c) {
                start++;
            }
            if (start != end) start++;
            return start;
        }

        static bool is_spec(char c) {
            return c == '\n' || c == '\r' || c == '\0' || c == '\t' || c == ' ';
        }

        static bool append(siter begin, siter left, siter right) {
            bool prev_spec = (left == begin || is_spec(*(left - 1)));
            bool cur_spec = is_spec(*right);

            return (!cur_spec || !prev_spec);
        }

        static int days_from_civil(int y, int m, int d) {
            y -= m <= 2;
            int era = y / 400;
            int yoe = y - era * 400;  // [0, 399]
            int doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;  // [0, 365]
            int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;  // [0, 146096]
            return era * 146097 + doe - 719468;
        }

        static time_t mytimegm(tm const &t) {
            int year = t.tm_year + 1900;
            int month = t.tm_mon;  // 0-11
            if (month > 11) {
                year += month / 12;
                month %= 12;
            } else if (month < 0) {
                int years_diff = (11 - month) / 12;
                year -= years_diff;
                month += 12 * years_diff;
            }
            int days_since_1970 = days_from_civil(year, month + 1, t.tm_mday);
            return 60 * (60 * (24L * days_since_1970 + t.tm_hour) + t.tm_min) + t.tm_sec;
        }

    public:
        static void extract(std::string &s, std::unordered_map<std::string, std::string> &meta) {
            const siter beg = s.begin();
            siter left = beg;
            siter right = beg;
            const siter end = s.end();

            while (right != s.end()) {
                if (*right == '<') {
                    if (starts_with(right, end, META_PREFIX)) {
                        std::string field, content;
                        right = skip_until(right, end, '\"');
                        while (right != end && *right != '\"') {
                            field += *right;
                            right++;
                        }
                        if (right != end) right++;
                        right = skip_until(right, end, '\"');
                        while (right != s.end() && *right != '\"') {
                            content += *right;
                            right++;
                        }
                        meta[field] = content;
                        right = skip_until(right, end, '>');
                    } else {
                        right = skip_until(right, end, '>');
                    }
                } else {
                    if (append(beg, left, right)) {
                        *left = *right;
                        left++;
                    }
                    right++;
                }
            }
            s.resize(left - beg);
        }

        static void extract(std::string &s) {
            siter beg = s.begin();
            siter left = beg;
            siter right = beg;
            siter end = s.end();

            while (right != end) {
                if (*right == '<') {
                    right = skip_until(right, end, '>');
                } else {
                    if (append(beg, left, right)) {
                        *left = *right;
                        left++;
                    }
                    right++;
                }
            }
            s.resize(left - beg);
        }

        static uint64_t extract_time(std::string const &s) {
            std::tm t = {};
            std::istringstream ss(s);

            if (ss >> std::get_time(&t, "%Y-%m-%dT%H:%M:%S")) {
                return mytimegm(t);
            } else {
                return 0;
            }
        }
    };

}

#endif //TGSERVER_HTML_PARSER_H