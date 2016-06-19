//: Playground - noun: a place where people can play

import UIKit

var str = "Hello, playground"

class Taiyaki {
    var nakami = "あんこ"
    func sayNakami(){
        print("中身は" + nakami + "です。")
    }
}

var taiyaki = Taiyaki()
taiyaki.nakami = "クリーム"
taiyaki.sayNakami()