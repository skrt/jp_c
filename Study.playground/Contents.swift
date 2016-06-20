//: Playground - noun: a place where people can play

import UIKit

var str = "Hello, playground"

class Cat {
    func run(){
        print("走る")
    }
}

class Cheetah : Cat {
    override func run(){
        print("時速１００キロで")
        //super.run()
    }
}

var cheetah = Cheetah()
var cat = Cat()
cheetah.run()
cat.run()
