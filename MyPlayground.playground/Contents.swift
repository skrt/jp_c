print(1 + 1)
print(5 - 3)
print(3 * 3)
print(6 / 2)
print(7 % 3)

//地球の体積
print(4 / 3 * 3.14 * 6378 * 6378 * 6378)

var i = 3
print(i * i)
var x = 13
print(x * x)


for n in 1...9{
    print(3 * n)
}

var j = 0

for n in 1...100{
    j += n
}
print(j)

var arr = [95,70,80]
var all = 0

for test in arr{
    all += test
}

print(all)

var scoreAll = [
    1:" 国語",
    70:"数学",
    80:"英語"
]

scoreAll[70] = "物理"

print(scoreAll)

func rect(long:Int) -> Int {
    let area = long * long
    return area
}

var result = rect(3)
print(result)