#include "../firmware/MegaControlador/Dy50ResponseFilter.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
std::vector<uint8_t> packet(std::vector<uint8_t> data) {
 uint16_t len=data.size()+2, sum=7+(len>>8)+(len&255);
 std::vector<uint8_t> p={0xef,1,255,255,255,255,7,uint8_t(len>>8),uint8_t(len)};
 for(auto b:data) { p.push_back(b); sum+=b; }
 p.push_back(sum>>8); p.push_back(sum); return p;
}
void feed(Dy50ResponseFilter &f,const std::vector<uint8_t>& p) { for(auto b:p) f.feed(b); }
int main() {
 Dy50ResponseFilter f; auto good=packet({0,0,1,0,80});
 f.begin(0x1b); feed(f,good); assert(f.available()==int(good.size()));
 for(auto b:good) assert(f.read()==b); assert(f.available()==0);
 auto corrupt=good; corrupt[10]^=1; f.begin(0x1b); feed(f,corrupt); assert(!f.available());
 auto badAddress=good; badAddress[2]=0; f.begin(0x1b); feed(f,badAddress); assert(!f.available());
 auto shortSuccess=packet({0}); f.begin(0x1b); feed(f,shortSuccess); assert(!f.available());
 auto error=packet({9}); f.begin(0x1b); feed(f,error); assert(f.available()==int(error.size()));
 f.begin(1); feed(f,shortSuccess); assert(f.available()==int(shortSuccess.size()));
 auto badType=good; badType[6]=2; f.begin(0x1b); feed(f,badType); assert(!f.available());
 f.begin(0x0f); feed(f,good); assert(!f.available());
 auto params=packet(std::vector<uint8_t>(17,0)); f.begin(0x0f); feed(f,params); assert(f.available()==int(params.size()));
 puts("DY50 filter: checksum, address, type and length checks passed");
}
