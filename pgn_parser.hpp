#pragma once
#include <string>
#include <unordered_map>

class PgnParser
{
private:
    std::unordered_map<std::string, std::string> tags;
    std::string raw_moves;

public:
    PgnParser();
    bool parseFiles(const std::string& filename);
    const std::unordered_map<std::string, std::string>& getTags() const;
    std::string getRawMoves() const;
};