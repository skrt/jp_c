//: Playground - noun: a place where people can play

import UIKit

var x = 300


switch x {
    case 0 :
        "zero"
    case 1...9:
        "1桁"
    case 10...99:
        "2桁"
    case 100...999:
        "3桁"
    default:
        "無いよ"
}

for _ in 1...10{
    x += 2
}


for var i = 0;i < 10;i++ {
    x += 2
}


var n:Int = 0

while 10 > n++ {
    "index:" + String(n)
}

let friend = ["さとう","さいとう","こばやし"]
var m:Int = 0
repeat {
    print(friend[m])
    m++
} while(m < friend.count)
